from __future__ import annotations

import argparse
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from .cli import run_migrate_e2e
from .runner_service import (
    BatchScheduledHook,
    CooperativeCancelHook,
    JOB_STATUS_VALUES,
    OrchestratorApiError,
    OrchestratorJobRequest,
    PipelineRunner,
    RunnerService,
)

_JOB_PATTERN = re.compile(r"^/jobs/(?P<job_id>[^/]+)$")
_JOB_LOGS_PATTERN = re.compile(r"^/jobs/(?P<job_id>[^/]+)/logs$")
_JOB_ARTIFACTS_PATTERN = re.compile(r"^/jobs/(?P<job_id>[^/]+)/artifacts$")
_JOB_CANCEL_PATTERN = re.compile(r"^/jobs/(?P<job_id>[^/]+)/cancel$")


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class OrchestratorService(RunnerService):
    """Backward-compatible orchestrator facade bound to cli.run_migrate_e2e."""

    def __init__(
        self,
        workspace_root: str | Path | None = None,
        *,
        job_store_path: str | Path | None = None,
        pipeline_runner: PipelineRunner | None = None,
        cooperative_cancel_hook: CooperativeCancelHook | None = None,
        batch_scheduled_hook: BatchScheduledHook | None = None,
    ) -> None:
        super().__init__(
            workspace_root=workspace_root,
            job_store_path=job_store_path,
            pipeline_runner=pipeline_runner or (lambda namespace: run_migrate_e2e(namespace)),
            cooperative_cancel_hook=cooperative_cancel_hook,
            batch_scheduled_hook=batch_scheduled_hook,
        )


class OrchestratorHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        request_handler: type[BaseHTTPRequestHandler],
        *,
        service: RunnerService,
    ) -> None:
        super().__init__(server_address, request_handler)
        self.orchestrator_service = service

    def server_close(self) -> None:
        try:
            self.orchestrator_service.shutdown()
        finally:
            super().server_close()


def _build_handler(service: RunnerService) -> type[BaseHTTPRequestHandler]:
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
    service: RunnerService | None = None,
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


__all__ = [
    "OrchestratorApiError",
    "OrchestratorHttpServer",
    "OrchestratorJobRequest",
    "OrchestratorService",
    "RunnerService",
    "build_arg_parser",
    "create_orchestrator_http_server",
    "main",
    "run_orchestrator_http_server",
]


if __name__ == "__main__":
    raise SystemExit(main())
