from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from queue import Empty, Queue
import re
import shutil
import threading
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from .cli import UI_RENDER_POLICY_MODE_CHOICES, run_migrate_e2e

JobStatus = Literal["queued", "running", "succeeded", "failed", "canceled"]

JOB_STATUS_VALUES: set[str] = {"queued", "running", "succeeded", "failed", "canceled"}
TERMINAL_JOB_STATUSES: set[str] = {"succeeded", "failed", "canceled"}
PIPELINE_STAGE_ORDER: tuple[str, ...] = (
    "parse",
    "map_api",
    "gen_ui",
    "fidelity_audit",
    "sync_preview",
    "preview_smoke",
)
PREVIEW_HOST_COPY_IGNORE_PATTERNS: tuple[str, ...] = ("node_modules", ".vite", "*.tsbuildinfo")

_JOB_PATTERN = re.compile(r"^/jobs/(?P<job_id>[^/]+)$")
_JOB_LOGS_PATTERN = re.compile(r"^/jobs/(?P<job_id>[^/]+)/logs$")
_JOB_ARTIFACTS_PATTERN = re.compile(r"^/jobs/(?P<job_id>[^/]+)/artifacts$")
_JOB_CANCEL_PATTERN = re.compile(r"^/jobs/(?P<job_id>[^/]+)/cancel$")
_JOB_STORE_VERSION = 1


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_report_stem(xml_path: Path) -> str:
    raw = xml_path.stem.strip()
    if not raw:
        return "screen"
    stem = "".join(ch if (ch.isalnum() or ch in {"-", "_"}) else "-" for ch in raw)
    stem = stem.strip("-_")
    return stem or "screen"


def _default_summary_out(xml_path: str, out_dir: str) -> Path:
    source = Path(xml_path)
    target_dir = Path(out_dir)
    stem = _normalize_report_stem(source)
    return target_dir / f"{stem}.migration-summary.json"


def _as_abs_path(path: Path, workspace_root: Path) -> Path:
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = workspace_root / candidate
    return candidate.resolve()


class OrchestratorApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "error": {
                "code": self.code,
                "message": self.message,
            }
        }
        if self.details:
            payload["error"]["details"] = self.details
        return payload


@dataclass(frozen=True)
class OrchestratorJobRequest:
    xml_path: str
    out_dir: str
    api_out_dir: str
    ui_out_dir: str
    preview_host_dir: str
    summary_out: str | None
    parse_report_out: str | None
    map_report_out: str | None
    ui_report_out: str | None
    fidelity_report_out: str | None
    preview_report_out: str | None
    manifest_file: str | None
    registry_generated_file: str | None
    known_tags_file: str | None
    known_attrs_file: str | None
    strict: bool
    capture_text: bool
    disable_roundtrip_gate: bool
    roundtrip_mismatch_limit: int
    render_policy_mode: str
    auto_risk_threshold: float | None
    pretty: bool
    use_isolated_preview_host: bool
    preview_host_source_dir: str | None

    def to_cli_namespace(self) -> argparse.Namespace:
        return argparse.Namespace(
            xml_path=self.xml_path,
            out_dir=self.out_dir,
            summary_out=self.summary_out,
            parse_report_out=self.parse_report_out,
            map_report_out=self.map_report_out,
            ui_report_out=self.ui_report_out,
            fidelity_report_out=self.fidelity_report_out,
            preview_report_out=self.preview_report_out,
            api_out_dir=self.api_out_dir,
            ui_out_dir=self.ui_out_dir,
            preview_host_dir=self.preview_host_dir,
            manifest_file=self.manifest_file,
            registry_generated_file=self.registry_generated_file,
            strict=self.strict,
            capture_text=self.capture_text,
            known_tags_file=self.known_tags_file,
            known_attrs_file=self.known_attrs_file,
            disable_roundtrip_gate=self.disable_roundtrip_gate,
            roundtrip_mismatch_limit=self.roundtrip_mismatch_limit,
            render_policy_mode=self.render_policy_mode,
            auto_risk_threshold=self.auto_risk_threshold,
            pretty=self.pretty,
        )

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "xml_path": self.xml_path,
            "out_dir": self.out_dir,
            "api_out_dir": self.api_out_dir,
            "ui_out_dir": self.ui_out_dir,
            "preview_host_dir": self.preview_host_dir,
            "summary_out": self.summary_out,
            "parse_report_out": self.parse_report_out,
            "map_report_out": self.map_report_out,
            "ui_report_out": self.ui_report_out,
            "fidelity_report_out": self.fidelity_report_out,
            "preview_report_out": self.preview_report_out,
            "manifest_file": self.manifest_file,
            "registry_generated_file": self.registry_generated_file,
            "known_tags_file": self.known_tags_file,
            "known_attrs_file": self.known_attrs_file,
            "strict": self.strict,
            "capture_text": self.capture_text,
            "disable_roundtrip_gate": self.disable_roundtrip_gate,
            "roundtrip_mismatch_limit": self.roundtrip_mismatch_limit,
            "render_policy_mode": self.render_policy_mode,
            "auto_risk_threshold": self.auto_risk_threshold,
            "pretty": self.pretty,
            "use_isolated_preview_host": self.use_isolated_preview_host,
            "preview_host_source_dir": self.preview_host_source_dir,
        }


@dataclass
class _JobState:
    job_id: str
    status: JobStatus
    created_at_utc: str
    updated_at_utc: str
    request: OrchestratorJobRequest
    request_payload: dict[str, Any]
    logs: list[dict[str, Any]] = field(default_factory=list)
    log_sequence: int = 0
    exit_code: int | None = None
    summary_file: str | None = None
    summary_payload: dict[str, Any] | None = None
    completed_at_utc: str | None = None
    error: dict[str, Any] | None = None
    cancel_requested: bool = False
    cancel_requested_at_utc: str | None = None


class OrchestratorService:
    def __init__(
        self,
        workspace_root: str | Path | None = None,
        *,
        job_store_path: str | Path | None = None,
    ) -> None:
        root = Path.cwd() if workspace_root is None else Path(workspace_root)
        self.workspace_root = root.resolve()
        self._job_store_path = (
            _as_abs_path(Path(job_store_path), self.workspace_root)
            if job_store_path is not None
            else (self.workspace_root / "out" / "orchestrator" / "jobs.json").resolve()
        )

        self._jobs: dict[str, _JobState] = {}
        self._lock = threading.Lock()
        self._queue: Queue[str | None] = Queue()
        self._shutdown_event = threading.Event()
        with self._lock:
            self._load_jobs_from_store_locked()
        self._worker = threading.Thread(
            target=self._run_worker,
            name="mifl-orchestrator-worker",
            daemon=True,
        )
        self._worker.start()

    def shutdown(self) -> None:
        if self._shutdown_event.is_set():
            return
        self._shutdown_event.set()
        self._queue.put(None)
        self._worker.join(timeout=2.0)

    def create_job(self, payload: object) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise OrchestratorApiError(
                400,
                code="invalid_payload",
                message="Request body must be a JSON object.",
            )

        job_id = uuid4().hex
        request = self._build_job_request(payload, job_id=job_id)
        now = _utc_now_iso()
        job = _JobState(
            job_id=job_id,
            status="queued",
            created_at_utc=now,
            updated_at_utc=now,
            request=request,
            request_payload=request.to_public_dict(),
        )
        with self._lock:
            self._jobs[job_id] = job
            self._append_log_locked(
                job,
                level="info",
                event="job_queued",
                message="Job accepted and queued.",
            )
            self._persist_jobs_locked()
        self._queue.put(job_id)
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise OrchestratorApiError(
                    404,
                    code="job_not_found",
                    message=f"Job not found: {job_id}",
                    details={"job_id": job_id},
                )
            return self._job_to_dict(job)

    def list_jobs(
        self,
        *,
        limit: int = 50,
        status_filter: set[str] | None = None,
    ) -> dict[str, Any]:
        if limit <= 0:
            raise OrchestratorApiError(
                400,
                code="validation_error",
                message="`limit` must be a positive integer.",
                details={"field": "limit", "minimum": 1, "actual": limit},
            )
        if status_filter:
            invalid_statuses = sorted(status for status in status_filter if status not in JOB_STATUS_VALUES)
            if invalid_statuses:
                raise OrchestratorApiError(
                    400,
                    code="validation_error",
                    message=f"`status` must be one of {sorted(JOB_STATUS_VALUES)}.",
                    details={"field": "status", "actual": invalid_statuses},
                )

        with self._lock:
            selected = sorted(
                self._jobs.values(),
                key=lambda item: (item.created_at_utc, item.job_id),
                reverse=True,
            )
            if status_filter:
                selected = [job for job in selected if job.status in status_filter]
            total = len(selected)
            jobs = [self._job_to_dict(job) for job in selected[:limit]]

        response: dict[str, Any] = {
            "jobs": jobs,
            "total": total,
            "limit": limit,
        }
        if status_filter:
            response["status_filter"] = sorted(status_filter)
        return response

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise OrchestratorApiError(
                    404,
                    code="job_not_found",
                    message=f"Job not found: {job_id}",
                    details={"job_id": job_id},
                )

            if job.status in TERMINAL_JOB_STATUSES:
                return self._job_to_dict(job)

            now = _utc_now_iso()
            job.cancel_requested = True
            job.cancel_requested_at_utc = job.cancel_requested_at_utc or now

            if job.status == "queued":
                self._mark_job_canceled_locked(
                    job,
                    message="Job canceled before execution.",
                    event="job_canceled",
                )
            else:
                self._append_log_locked(
                    job,
                    level="info",
                    event="cancel_requested",
                    message="Cancel request accepted for running job.",
                )
            self._persist_jobs_locked()
            return self._job_to_dict(job)

    def _mark_job_canceled_locked(
        self,
        job: _JobState,
        *,
        message: str,
        event: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        now = _utc_now_iso()
        job.status = "canceled"
        job.completed_at_utc = now
        job.updated_at_utc = now

        error_details: dict[str, Any] = {"job_id": job.job_id}
        if job.cancel_requested_at_utc:
            error_details["requested_at_utc"] = job.cancel_requested_at_utc
        if details:
            error_details.update(details)

        job.error = {
            "code": "job_canceled",
            "message": message,
            "details": error_details,
        }
        self._append_log_locked(
            job,
            level="info",
            event=event,
            message=message,
            details=error_details,
        )

    def get_job_logs(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise OrchestratorApiError(
                    404,
                    code="job_not_found",
                    message=f"Job not found: {job_id}",
                    details={"job_id": job_id},
                )
            return {
                "job_id": job.job_id,
                "status": job.status,
                "logs": list(job.logs),
            }

    def get_job_artifacts(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise OrchestratorApiError(
                    404,
                    code="job_not_found",
                    message=f"Job not found: {job_id}",
                    details={"job_id": job_id},
                )
            status = job.status
            summary_file = job.summary_file
            summary_payload = job.summary_payload

        if status not in TERMINAL_JOB_STATUSES:
            raise OrchestratorApiError(
                409,
                code="job_not_completed",
                message=f"Artifacts are not available while job is {status}.",
                details={"job_id": job_id, "status": status},
            )

        if summary_payload is None and summary_file:
            summary_path = Path(summary_file)
            if summary_path.exists():
                summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
                with self._lock:
                    job = self._jobs.get(job_id)
                    if job is not None:
                        job.summary_payload = summary_payload
                        self._persist_jobs_locked()

        if summary_payload is None:
            raise OrchestratorApiError(
                404,
                code="artifacts_not_found",
                message="Summary artifacts were not found for this job.",
                details={"job_id": job_id, "summary_file": summary_file},
            )

        return {
            "job_id": job_id,
            "status": status,
            "artifacts": {
                "summary_file": summary_file,
                "overall_status": summary_payload.get("overall_status"),
                "overall_exit_code": summary_payload.get("overall_exit_code"),
                "reports": summary_payload.get("reports", {}),
                "stages": summary_payload.get("stages", {}),
                "generated_file_references": summary_payload.get("generated_file_references", []),
                "warnings": summary_payload.get("warnings", []),
                "errors": summary_payload.get("errors", []),
            },
        }

    def _build_job_request(self, payload: dict[str, Any], *, job_id: str) -> OrchestratorJobRequest:
        xml_path_raw = self._required_non_empty_string(payload, "xml_path")
        xml_path = _as_abs_path(Path(xml_path_raw), self.workspace_root)
        if not xml_path.exists() or not xml_path.is_file():
            raise OrchestratorApiError(
                400,
                code="invalid_xml_path",
                message="`xml_path` must point to an existing file.",
                details={"xml_path": str(xml_path)},
            )

        job_root = self.workspace_root / "out" / "jobs" / job_id

        out_dir = self._optional_path(payload, "out_dir", default=job_root / "e2e")
        api_out_dir = self._optional_path(payload, "api_out_dir", default=job_root / "generated-api")
        ui_out_dir = self._optional_path(payload, "ui_out_dir", default=job_root / "generated-ui")

        preview_host_dir_raw = self._optional_non_empty_string(payload, "preview_host_dir")
        use_isolated_preview_host = self._optional_bool(
            payload,
            "use_isolated_preview_host",
            default=preview_host_dir_raw is None,
        )
        preview_host_source_raw = self._optional_non_empty_string(payload, "preview_host_source_dir")

        if use_isolated_preview_host:
            source_dir = (
                _as_abs_path(Path(preview_host_source_raw), self.workspace_root)
                if preview_host_source_raw
                else (self.workspace_root / "preview-host").resolve()
            )
            if not source_dir.exists() or not source_dir.is_dir():
                raise OrchestratorApiError(
                    400,
                    code="invalid_preview_host_source_dir",
                    message="`preview_host_source_dir` must point to an existing directory.",
                    details={"preview_host_source_dir": str(source_dir)},
                )
            preview_host_dir = (
                _as_abs_path(Path(preview_host_dir_raw), self.workspace_root)
                if preview_host_dir_raw
                else (job_root / "preview-host").resolve()
            )
            preview_host_source_dir = str(source_dir)
        else:
            preview_host_dir = (
                _as_abs_path(Path(preview_host_dir_raw), self.workspace_root)
                if preview_host_dir_raw
                else (self.workspace_root / "preview-host").resolve()
            )
            if not preview_host_dir.exists() or not preview_host_dir.is_dir():
                raise OrchestratorApiError(
                    400,
                    code="invalid_preview_host_dir",
                    message="`preview_host_dir` must point to an existing directory when isolation is disabled.",
                    details={"preview_host_dir": str(preview_host_dir)},
                )
            preview_host_source_dir = None

        if use_isolated_preview_host and preview_host_source_dir == str(preview_host_dir):
            raise OrchestratorApiError(
                400,
                code="invalid_preview_host_config",
                message="`preview_host_dir` must differ from `preview_host_source_dir` when isolation is enabled.",
                details={
                    "preview_host_dir": str(preview_host_dir),
                    "preview_host_source_dir": preview_host_source_dir,
                },
            )

        known_tags_file = self._optional_existing_file(payload, "known_tags_file")
        known_attrs_file = self._optional_existing_file(payload, "known_attrs_file")

        strict = self._optional_bool(payload, "strict", default=False)
        capture_text = self._optional_bool(payload, "capture_text", default=False)
        disable_roundtrip_gate = self._optional_bool(payload, "disable_roundtrip_gate", default=False)
        pretty = self._optional_bool(payload, "pretty", default=True)
        roundtrip_mismatch_limit = self._optional_int(
            payload,
            "roundtrip_mismatch_limit",
            default=200,
            minimum=0,
        )
        render_policy_mode = self._optional_choice_string(
            payload,
            "render_policy_mode",
            choices=UI_RENDER_POLICY_MODE_CHOICES,
            default="mui",
        )
        auto_risk_threshold = self._optional_unit_interval(payload, "auto_risk_threshold")

        summary_out = self._optional_path(payload, "summary_out")
        parse_report_out = self._optional_path(payload, "parse_report_out")
        map_report_out = self._optional_path(payload, "map_report_out")
        ui_report_out = self._optional_path(payload, "ui_report_out")
        fidelity_report_out = self._optional_path(payload, "fidelity_report_out")
        preview_report_out = self._optional_path(payload, "preview_report_out")
        manifest_file = self._optional_path(payload, "manifest_file")
        registry_generated_file = self._optional_path(payload, "registry_generated_file")

        return OrchestratorJobRequest(
            xml_path=str(xml_path),
            out_dir=str(out_dir),
            api_out_dir=str(api_out_dir),
            ui_out_dir=str(ui_out_dir),
            preview_host_dir=str(preview_host_dir),
            summary_out=str(summary_out) if summary_out else None,
            parse_report_out=str(parse_report_out) if parse_report_out else None,
            map_report_out=str(map_report_out) if map_report_out else None,
            ui_report_out=str(ui_report_out) if ui_report_out else None,
            fidelity_report_out=str(fidelity_report_out) if fidelity_report_out else None,
            preview_report_out=str(preview_report_out) if preview_report_out else None,
            manifest_file=str(manifest_file) if manifest_file else None,
            registry_generated_file=str(registry_generated_file) if registry_generated_file else None,
            known_tags_file=known_tags_file,
            known_attrs_file=known_attrs_file,
            strict=strict,
            capture_text=capture_text,
            disable_roundtrip_gate=disable_roundtrip_gate,
            roundtrip_mismatch_limit=roundtrip_mismatch_limit,
            render_policy_mode=render_policy_mode,
            auto_risk_threshold=auto_risk_threshold,
            pretty=pretty,
            use_isolated_preview_host=use_isolated_preview_host,
            preview_host_source_dir=preview_host_source_dir,
        )

    def _required_non_empty_string(self, payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise OrchestratorApiError(
                400,
                code="validation_error",
                message=f"`{key}` is required and must be a non-empty string.",
                details={"field": key},
            )
        return value.strip()

    def _optional_non_empty_string(self, payload: dict[str, Any], key: str) -> str | None:
        value = payload.get(key)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise OrchestratorApiError(
                400,
                code="validation_error",
                message=f"`{key}` must be a non-empty string when provided.",
                details={"field": key},
            )
        return value.strip()

    def _optional_bool(self, payload: dict[str, Any], key: str, *, default: bool) -> bool:
        value = payload.get(key, default)
        if not isinstance(value, bool):
            raise OrchestratorApiError(
                400,
                code="validation_error",
                message=f"`{key}` must be a boolean.",
                details={"field": key},
            )
        return value

    def _optional_int(
        self,
        payload: dict[str, Any],
        key: str,
        *,
        default: int,
        minimum: int | None = None,
    ) -> int:
        value = payload.get(key, default)
        if not isinstance(value, int):
            raise OrchestratorApiError(
                400,
                code="validation_error",
                message=f"`{key}` must be an integer.",
                details={"field": key},
            )
        if minimum is not None and value < minimum:
            raise OrchestratorApiError(
                400,
                code="validation_error",
                message=f"`{key}` must be greater than or equal to {minimum}.",
                details={"field": key, "minimum": minimum, "actual": value},
            )
        return value

    def _optional_unit_interval(self, payload: dict[str, Any], key: str) -> float | None:
        value = payload.get(key)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise OrchestratorApiError(
                400,
                code="validation_error",
                message=f"`{key}` must be a number between 0.0 and 1.0.",
                details={"field": key},
            )
        numeric = float(value)
        if numeric < 0.0 or numeric > 1.0:
            raise OrchestratorApiError(
                400,
                code="validation_error",
                message=f"`{key}` must be between 0.0 and 1.0.",
                details={"field": key, "actual": numeric},
            )
        return numeric

    def _optional_choice_string(
        self,
        payload: dict[str, Any],
        key: str,
        *,
        choices: tuple[str, ...],
        default: str,
    ) -> str:
        value = payload.get(key, default)
        if not isinstance(value, str) or not value.strip():
            raise OrchestratorApiError(
                400,
                code="validation_error",
                message=f"`{key}` must be a non-empty string.",
                details={"field": key},
            )
        normalized = value.strip()
        if normalized not in choices:
            raise OrchestratorApiError(
                400,
                code="validation_error",
                message=f"`{key}` must be one of {sorted(choices)}.",
                details={"field": key, "allowed": sorted(choices), "actual": normalized},
            )
        return normalized

    def _optional_existing_file(self, payload: dict[str, Any], key: str) -> str | None:
        value = self._optional_non_empty_string(payload, key)
        if value is None:
            return None
        file_path = _as_abs_path(Path(value), self.workspace_root)
        if not file_path.exists() or not file_path.is_file():
            raise OrchestratorApiError(
                400,
                code="validation_error",
                message=f"`{key}` must point to an existing file.",
                details={"field": key, "path": str(file_path)},
            )
        return str(file_path)

    def _optional_path(
        self,
        payload: dict[str, Any],
        key: str,
        *,
        default: Path | None = None,
    ) -> Path | None:
        value = self._optional_non_empty_string(payload, key)
        if value is None:
            return default.resolve() if default is not None else None
        return _as_abs_path(Path(value), self.workspace_root)

    def _load_jobs_from_store_locked(self) -> None:
        if not self._job_store_path.exists():
            return
        try:
            raw = json.loads(self._job_store_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, dict):
            return
        raw_jobs = raw.get("jobs")
        if not isinstance(raw_jobs, list):
            return

        loaded_jobs: list[_JobState] = []
        for raw_job in raw_jobs:
            if not isinstance(raw_job, dict):
                continue
            parsed = self._job_state_from_record(raw_job)
            if parsed is not None:
                loaded_jobs.append(parsed)

        loaded_jobs.sort(key=lambda item: (item.created_at_utc, item.job_id))
        self._jobs = {job.job_id: job for job in loaded_jobs}

        if self._recover_incomplete_jobs_locked():
            self._persist_jobs_locked()

    def _recover_incomplete_jobs_locked(self) -> bool:
        changed = False
        for job in self._jobs.values():
            if job.status in TERMINAL_JOB_STATUSES:
                continue
            previous_status = job.status
            now = _utc_now_iso()
            job.status = "failed"
            job.completed_at_utc = now
            job.updated_at_utc = now
            job.error = {
                "code": "job_incomplete_after_restart",
                "message": "Job did not complete before orchestrator restart.",
                "details": {"previous_status": previous_status},
            }
            self._append_log_locked(
                job,
                level="error",
                event="job_incomplete_after_restart",
                message="Job was marked as failed after orchestrator restart.",
                details={"previous_status": previous_status},
            )
            changed = True
        return changed

    def _job_state_to_record(self, job: _JobState) -> dict[str, Any]:
        return {
            "job_id": job.job_id,
            "status": job.status,
            "created_at_utc": job.created_at_utc,
            "updated_at_utc": job.updated_at_utc,
            "request": job.request.to_public_dict(),
            "request_payload": job.request_payload,
            "logs": job.logs,
            "log_sequence": job.log_sequence,
            "exit_code": job.exit_code,
            "summary_file": job.summary_file,
            "summary_payload": job.summary_payload,
            "completed_at_utc": job.completed_at_utc,
            "error": job.error,
            "cancel_requested": job.cancel_requested,
            "cancel_requested_at_utc": job.cancel_requested_at_utc,
        }

    def _job_state_from_record(self, record: dict[str, Any]) -> _JobState | None:
        job_id_raw = record.get("job_id", record.get("id"))
        if not isinstance(job_id_raw, str) or not job_id_raw:
            return None

        status_raw = record.get("status")
        if status_raw not in JOB_STATUS_VALUES:
            return None

        request_raw = record.get("request_payload")
        if not isinstance(request_raw, dict):
            request_raw = record.get("request")
        if not isinstance(request_raw, dict):
            return None

        request_payload = dict(request_raw)
        request_payload.setdefault("auto_risk_threshold", None)

        try:
            request = OrchestratorJobRequest(**request_payload)
        except TypeError:
            return None

        created_at_raw = record.get("created_at_utc")
        created_at = created_at_raw if isinstance(created_at_raw, str) and created_at_raw else _utc_now_iso()
        updated_at_raw = record.get("updated_at_utc")
        updated_at = updated_at_raw if isinstance(updated_at_raw, str) and updated_at_raw else created_at

        logs_raw = record.get("logs", [])
        logs = [entry for entry in logs_raw if isinstance(entry, dict)] if isinstance(logs_raw, list) else []

        log_sequence_raw = record.get("log_sequence", len(logs))
        log_sequence = log_sequence_raw if isinstance(log_sequence_raw, int) and log_sequence_raw >= 0 else len(logs)

        exit_code_raw = record.get("exit_code")
        summary_payload_raw = record.get("summary_payload")
        completed_at_raw = record.get("completed_at_utc")
        error_raw = record.get("error")
        cancel_requested_at_raw = record.get("cancel_requested_at_utc")

        return _JobState(
            job_id=job_id_raw,
            status=status_raw,
            created_at_utc=created_at,
            updated_at_utc=updated_at,
            request=request,
            request_payload=request_payload,
            logs=logs,
            log_sequence=log_sequence,
            exit_code=exit_code_raw if isinstance(exit_code_raw, int) else None,
            summary_file=record.get("summary_file") if isinstance(record.get("summary_file"), str) else None,
            summary_payload=summary_payload_raw if isinstance(summary_payload_raw, dict) else None,
            completed_at_utc=completed_at_raw if isinstance(completed_at_raw, str) else None,
            error=error_raw if isinstance(error_raw, dict) else None,
            cancel_requested=bool(record.get("cancel_requested", False)),
            cancel_requested_at_utc=(
                cancel_requested_at_raw if isinstance(cancel_requested_at_raw, str) else None
            ),
        )

    def _persist_jobs_locked(self) -> None:
        snapshot = {
            "version": _JOB_STORE_VERSION,
            "updated_at_utc": _utc_now_iso(),
            "jobs": [
                self._job_state_to_record(job)
                for job in sorted(self._jobs.values(), key=lambda item: (item.created_at_utc, item.job_id))
            ],
        }
        self._job_store_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._job_store_path.with_suffix(f"{self._job_store_path.suffix}.tmp")
        try:
            temp_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
            temp_path.replace(self._job_store_path)
        except OSError:
            return

    def _run_worker(self) -> None:
        while True:
            if self._shutdown_event.is_set() and self._queue.empty():
                break
            try:
                job_id = self._queue.get(timeout=0.1)
            except Empty:
                continue
            if job_id is None:
                self._queue.task_done()
                break
            self._execute_job(job_id)
            self._queue.task_done()

    def _execute_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if job.status == "canceled":
                return
            if job.cancel_requested:
                self._mark_job_canceled_locked(
                    job,
                    message="Job canceled before execution.",
                    event="job_canceled",
                )
                self._persist_jobs_locked()
                return
            job.status = "running"
            job.updated_at_utc = _utc_now_iso()
            self._append_log_locked(
                job,
                level="info",
                event="job_started",
                message="Job execution started.",
            )
            request = job.request
            self._persist_jobs_locked()

        try:
            if request.use_isolated_preview_host:
                self._prepare_isolated_preview_host(request)
                with self._lock:
                    current = self._jobs.get(job_id)
                    if current is not None:
                        if current.cancel_requested:
                            self._mark_job_canceled_locked(
                                current,
                                message="Job canceled before pipeline execution.",
                                event="job_canceled",
                            )
                            self._persist_jobs_locked()
                            return
                        self._append_log_locked(
                            current,
                            level="info",
                            event="preview_host_prepared",
                            message="Isolated preview-host workspace prepared.",
                            details={"preview_host_dir": request.preview_host_dir},
                        )
                        self._persist_jobs_locked()

            with self._lock:
                current = self._jobs.get(job_id)
                if current is not None:
                    if current.cancel_requested:
                        self._mark_job_canceled_locked(
                            current,
                            message="Job canceled before pipeline execution.",
                            event="job_canceled",
                        )
                        self._persist_jobs_locked()
                        return
                    self._append_log_locked(
                        current,
                        level="info",
                        event="pipeline_started",
                        message="Running migrate-e2e pipeline.",
                    )
                    self._persist_jobs_locked()

            exit_code = run_migrate_e2e(request.to_cli_namespace())
            summary_path = (
                Path(request.summary_out)
                if request.summary_out
                else _default_summary_out(request.xml_path, request.out_dir)
            )
            summary_payload = None
            if summary_path.exists():
                summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))

            completion_error: dict[str, Any] | None = None
            completion_status: JobStatus
            if exit_code == 0 and summary_payload is not None:
                completion_status = "succeeded"
            elif exit_code == 0 and summary_payload is None:
                completion_status = "failed"
                completion_error = {
                    "code": "summary_not_found",
                    "message": "Pipeline completed but summary artifact was not found.",
                    "details": {"summary_file": str(summary_path)},
                }
            else:
                completion_status = "failed"
                completion_error = {
                    "code": "pipeline_failed",
                    "message": f"migrate-e2e exited with code {exit_code}.",
                    "details": {"exit_code": exit_code, "summary_file": str(summary_path)},
                }

            with self._lock:
                current = self._jobs.get(job_id)
                if current is None:
                    return
                now = _utc_now_iso()
                current.exit_code = exit_code
                current.summary_file = str(summary_path)
                current.summary_payload = summary_payload
                current.updated_at_utc = now
                if current.cancel_requested:
                    self._mark_job_canceled_locked(
                        current,
                        message="Job canceled by request.",
                        event="job_canceled",
                        details={
                            "exit_code": exit_code,
                            "summary_file": str(summary_path),
                        },
                    )
                    self._persist_jobs_locked()
                    return
                current.status = completion_status
                current.completed_at_utc = now
                current.error = completion_error
                level = "info" if completion_status == "succeeded" else "error"
                self._append_log_locked(
                    current,
                    level=level,
                    event="job_finished",
                    message=(
                        "Job completed successfully."
                        if completion_status == "succeeded"
                        else "Job completed with failures."
                    ),
                    details={"exit_code": exit_code, "summary_file": str(summary_path)},
                )
                self._persist_jobs_locked()
        except Exception as exc:  # pragma: no cover - defensive path
            with self._lock:
                current = self._jobs.get(job_id)
                if current is None:
                    return
                if current.cancel_requested:
                    self._mark_job_canceled_locked(
                        current,
                        message="Job canceled by request.",
                        event="job_canceled",
                        details={
                            "exception_type": type(exc).__name__,
                            "exception_message": str(exc),
                        },
                    )
                else:
                    now = _utc_now_iso()
                    current.status = "failed"
                    current.completed_at_utc = now
                    current.updated_at_utc = now
                    current.error = {
                        "code": "job_execution_exception",
                        "message": f"{type(exc).__name__}: {exc}",
                    }
                    self._append_log_locked(
                        current,
                        level="error",
                        event="job_exception",
                        message="Unhandled exception during job execution.",
                        details={"exception_type": type(exc).__name__, "exception_message": str(exc)},
                    )
                self._persist_jobs_locked()

    def _prepare_isolated_preview_host(self, request: OrchestratorJobRequest) -> None:
        source_raw = request.preview_host_source_dir
        if source_raw is None:
            return
        source_dir = Path(source_raw)
        target_dir = Path(request.preview_host_dir)
        if target_dir.exists():
            return
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            source_dir,
            target_dir,
            ignore=shutil.ignore_patterns(*PREVIEW_HOST_COPY_IGNORE_PATTERNS),
        )

    def _append_log_locked(
        self,
        job: _JobState,
        *,
        level: str,
        event: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        job.log_sequence += 1
        now = _utc_now_iso()
        entry: dict[str, Any] = {
            "sequence": job.log_sequence,
            "timestamp_utc": now,
            "level": level,
            "event": event,
            "message": message,
        }
        if details:
            entry["details"] = details
        job.logs.append(entry)
        job.updated_at_utc = now

    def _job_to_dict(self, job: _JobState) -> dict[str, Any]:
        result: dict[str, Any] | None
        if job.exit_code is None:
            result = None
        else:
            summary_payload = job.summary_payload or {}
            result = {
                "exit_code": job.exit_code,
                "summary_file": job.summary_file,
                "completed_at_utc": job.completed_at_utc,
                "summary_overview": {
                    "overall_status": summary_payload.get("overall_status"),
                    "overall_exit_code": summary_payload.get("overall_exit_code"),
                },
            }

        payload: dict[str, Any] = {
            "id": job.job_id,
            "status": job.status,
            "created_at_utc": job.created_at_utc,
            "updated_at_utc": job.updated_at_utc,
            "cancel_requested": job.cancel_requested,
            "cancel_requested_at_utc": job.cancel_requested_at_utc,
            "pipeline_stages": list(PIPELINE_STAGE_ORDER),
            "request": job.request_payload,
            "result": result,
        }
        if job.error is not None:
            payload["error"] = job.error
        return payload


class OrchestratorHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        request_handler: type[BaseHTTPRequestHandler],
        *,
        service: OrchestratorService,
    ) -> None:
        super().__init__(server_address, request_handler)
        self.orchestrator_service = service

    def server_close(self) -> None:
        try:
            self.orchestrator_service.shutdown()
        finally:
            super().server_close()


def _build_handler(service: OrchestratorService) -> type[BaseHTTPRequestHandler]:
    class OrchestratorHandler(BaseHTTPRequestHandler):
        server_version = "MiflMigratorOrchestrator/1.0"
        error_content_type = "application/json"

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = self._normalize_path(parsed.path)
            try:
                cancel_match = _JOB_CANCEL_PATTERN.match(path)
                if cancel_match:
                    job_id = cancel_match.group("job_id")
                    self._send_json(202, {"job": service.cancel_job(job_id)})
                    return

                if path == "/jobs":
                    payload = self._read_json_body()
                    job = service.create_job(payload)
                    self._send_json(202, {"job": job})
                    return
                self._raise_not_found(path)
            except OrchestratorApiError as exc:
                self._send_json(exc.status_code, exc.to_dict())
            except Exception as exc:  # pragma: no cover - defensive path
                self._send_json(
                    500,
                    {
                        "error": {
                            "code": "internal_error",
                            "message": f"{type(exc).__name__}: {exc}",
                        }
                    },
                )

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = self._normalize_path(parsed.path)
            query = parse_qs(parsed.query, keep_blank_values=True)
            try:
                if path == "/health":
                    self._send_json(
                        200,
                        {
                            "status": "ok",
                            "service": "mifl-migrator-orchestrator-api",
                            "time_utc": _utc_now_iso(),
                        },
                    )
                    return

                if path == "/jobs":
                    limit = self._parse_limit_query(query)
                    status_filter = self._parse_status_filter_query(query)
                    self._send_json(
                        200,
                        service.list_jobs(
                            limit=limit,
                            status_filter=status_filter,
                        ),
                    )
                    return

                job_match = _JOB_PATTERN.match(path)
                if job_match:
                    job_id = job_match.group("job_id")
                    self._send_json(200, {"job": service.get_job(job_id)})
                    return

                logs_match = _JOB_LOGS_PATTERN.match(path)
                if logs_match:
                    job_id = logs_match.group("job_id")
                    self._send_json(200, service.get_job_logs(job_id))
                    return

                artifacts_match = _JOB_ARTIFACTS_PATTERN.match(path)
                if artifacts_match:
                    job_id = artifacts_match.group("job_id")
                    self._send_json(200, service.get_job_artifacts(job_id))
                    return

                self._raise_not_found(path)
            except OrchestratorApiError as exc:
                self._send_json(exc.status_code, exc.to_dict())
            except Exception as exc:  # pragma: no cover - defensive path
                self._send_json(
                    500,
                    {
                        "error": {
                            "code": "internal_error",
                            "message": f"{type(exc).__name__}: {exc}",
                        }
                    },
                )

        def do_PUT(self) -> None:  # noqa: N802
            self._send_json(
                405,
                {
                    "error": {
                        "code": "method_not_allowed",
                        "message": "Method not allowed.",
                    }
                },
            )

        def do_DELETE(self) -> None:  # noqa: N802
            self._send_json(
                405,
                {
                    "error": {
                        "code": "method_not_allowed",
                        "message": "Method not allowed.",
                    }
                },
            )

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

        def _read_json_body(self) -> dict[str, Any]:
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                raise OrchestratorApiError(
                    400,
                    code="invalid_payload",
                    message="Request body is required.",
                )
            try:
                body_length = int(raw_length)
            except ValueError as exc:
                raise OrchestratorApiError(
                    400,
                    code="invalid_payload",
                    message="Invalid Content-Length header.",
                ) from exc

            raw_body = self.rfile.read(max(0, body_length))
            if not raw_body:
                return {}
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise OrchestratorApiError(
                    400,
                    code="invalid_json",
                    message="Request body must be valid JSON.",
                    details={"line": exc.lineno, "column": exc.colno},
                ) from exc

            if not isinstance(payload, dict):
                raise OrchestratorApiError(
                    400,
                    code="invalid_payload",
                    message="Request body must be a JSON object.",
                )
            return payload

        def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _normalize_path(self, path: str) -> str:
            normalized = path.rstrip("/")
            return normalized or "/"

        def _parse_limit_query(self, query: dict[str, list[str]]) -> int:
            raw_values = query.get("limit")
            if not raw_values:
                return 50
            raw = raw_values[-1].strip()
            try:
                value = int(raw)
            except ValueError as exc:
                raise OrchestratorApiError(
                    400,
                    code="validation_error",
                    message="`limit` must be a positive integer.",
                    details={"field": "limit", "actual": raw},
                ) from exc
            if value <= 0:
                raise OrchestratorApiError(
                    400,
                    code="validation_error",
                    message="`limit` must be a positive integer.",
                    details={"field": "limit", "minimum": 1, "actual": value},
                )
            return value

        def _parse_status_filter_query(self, query: dict[str, list[str]]) -> set[str] | None:
            raw_values = query.get("status")
            if not raw_values:
                return None
            tokens: list[str] = []
            for raw in raw_values:
                for candidate in raw.split(","):
                    normalized = candidate.strip()
                    if normalized:
                        tokens.append(normalized)
            if not tokens:
                raise OrchestratorApiError(
                    400,
                    code="validation_error",
                    message=f"`status` must be one of {sorted(JOB_STATUS_VALUES)}.",
                    details={"field": "status"},
                )
            invalid = sorted(token for token in tokens if token not in JOB_STATUS_VALUES)
            if invalid:
                raise OrchestratorApiError(
                    400,
                    code="validation_error",
                    message=f"`status` must be one of {sorted(JOB_STATUS_VALUES)}.",
                    details={"field": "status", "actual": invalid},
                )
            return set(tokens)

        def _raise_not_found(self, path: str) -> None:
            raise OrchestratorApiError(
                404,
                code="not_found",
                message=f"Endpoint not found: {path}",
                details={"path": path},
            )

    return OrchestratorHandler


def create_orchestrator_http_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    workspace_root: str | Path | None = None,
    job_store_path: str | Path | None = None,
    service: OrchestratorService | None = None,
) -> OrchestratorHttpServer:
    orchestrator_service = service or OrchestratorService(
        workspace_root=workspace_root,
        job_store_path=job_store_path,
    )
    handler = _build_handler(orchestrator_service)
    return OrchestratorHttpServer((host, port), handler, service=orchestrator_service)


def run_orchestrator_http_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    workspace_root: str | Path | None = None,
    job_store_path: str | Path | None = None,
) -> None:
    server = create_orchestrator_http_server(
        host=host,
        port=port,
        workspace_root=workspace_root,
        job_store_path=job_store_path,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return
    finally:
        server.shutdown()
        server.server_close()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mifl-migrator-api",
        description="Local asynchronous orchestrator API for mifl-migrator pipeline jobs.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    parser.add_argument(
        "--workspace-root",
        default=str(Path.cwd()),
        help="Workspace root used for resolving relative paths (default: current directory)",
    )
    parser.add_argument(
        "--job-store-path",
        default=None,
        help=(
            "Optional path to orchestrator job store JSON file "
            "(default: <workspace-root>/out/orchestrator/jobs.json)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    run_orchestrator_http_server(
        host=args.host,
        port=args.port,
        workspace_root=args.workspace_root,
        job_store_path=args.job_store_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
