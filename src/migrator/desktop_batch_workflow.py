from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Literal, Sequence

DEFAULT_XML_GLOB_PATTERN = "*.xml"
DEFAULT_DESKTOP_RUNS_DIRNAME = "desktop-runs"
DEFAULT_PROJECTS_DIRNAME = "projects"
PROJECT_MANIFEST_FILENAME = "project.json"
PROJECT_MANIFEST_CONTRACT_VERSION = 1
PROJECT_CONSOLIDATION_CONTRACT_VERSION = 1
COVERAGE_LEDGER_FILENAME = "coverage-ledger.json"
PROJECT_COVERAGE_LEDGER_CONTRACT_VERSION = 1
_PROJECT_COLLISION_HISTORY_LIMIT = 200
BATCH_SUMMARY_CONTRACT_VERSION = 1
_DEFAULT_RUN_ID_PREFIX = "run"
_DEFAULT_RETRY_RUN_ID_PREFIX = "retry"

BatchSourceMode = Literal["single_file", "folder", "explicit_queue"]
BatchItemStatus = Literal["queued", "running", "succeeded", "failed", "canceled", "skipped"]


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_abs_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def _sanitize_token(value: str, *, fallback: str) -> str:
    sanitized = "".join(ch if (ch.isalnum() or ch in {"-", "_"}) else "-" for ch in value.strip())
    sanitized = sanitized.strip("-_")
    return sanitized or fallback


def _normalize_glob_pattern(glob_pattern: str | None) -> str:
    if glob_pattern is None:
        return DEFAULT_XML_GLOB_PATTERN
    normalized = glob_pattern.strip()
    if not normalized:
        return DEFAULT_XML_GLOB_PATTERN
    return normalized


def _hash_text(value: str, *, length: int = 12) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()
    return digest[: max(1, length)]


def _build_queue_fingerprint(paths: Sequence[Path]) -> str:
    joined = "\n".join(str(path) for path in paths)
    return _hash_text(joined, length=16)


def _normalize_timestamp_slug(generated_at_utc: str) -> str:
    parsed = datetime.fromisoformat(generated_at_utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def build_batch_run_id(
    xml_paths: Sequence[str | Path],
    *,
    generated_at_utc: str | None = None,
    prefix: str = _DEFAULT_RUN_ID_PREFIX,
) -> str:
    if not xml_paths:
        raise ValueError("Cannot build run_id from an empty XML queue.")
    created_at = generated_at_utc or _utc_now_iso()
    stamp = _normalize_timestamp_slug(created_at)
    fingerprint = _hash_text(
        "\n".join(str(_normalize_abs_path(path)) for path in xml_paths),
        length=10,
    )
    return f"{_sanitize_token(prefix, fallback='run')}-{stamp}-{fingerprint}"


@dataclass(slots=True, frozen=True)
class BatchSourceSelection:
    source_mode: BatchSourceMode
    source_xml_file: str | None
    source_xml_dir: str | None
    recursive: bool
    glob_pattern: str


@dataclass(slots=True, frozen=True)
class BatchOutputLayout:
    output_root_dir: str
    runs_root_dir: str
    run_id: str
    run_root_dir: str
    plan_file: str
    summary_file: str
    project_key: str | None = None
    project_root_dir: str | None = None
    project_manifest_file: str | None = None


@dataclass(slots=True, frozen=True)
class BatchRunItemLayout:
    queue_index: int
    item_key: str
    item_root_dir: str
    out_dir: str
    api_out_dir: str
    ui_out_dir: str
    preview_host_dir: str
    summary_out: str


@dataclass(slots=True, frozen=True)
class BatchRunPlanItem:
    queue_index: int
    xml_path: str
    xml_stem: str
    source_relative_path: str | None
    path_digest: str
    output: BatchRunItemLayout


@dataclass(slots=True, frozen=True)
class BatchRunPlanSummary:
    generated_at_utc: str
    total_items: int
    source_mode: BatchSourceMode
    recursive: bool
    glob_pattern: str
    queue_fingerprint: str


@dataclass(slots=True, frozen=True)
class BatchRunPlan:
    contract_version: int
    run_id: str
    retry_of_run_id: str | None
    selection: BatchSourceSelection
    output: BatchOutputLayout
    items: list[BatchRunPlanItem]
    summary: BatchRunPlanSummary

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class BatchRunItemResult:
    queue_index: int
    xml_path: str
    status: BatchItemStatus
    exit_code: int | None = None
    summary_file: str | None = None
    error_message: str | None = None


@dataclass(slots=True, frozen=True)
class BatchSummaryViewItem:
    queue_index: int
    xml_path: str
    xml_stem: str
    status: BatchItemStatus
    exit_code: int | None
    summary_file: str | None
    error_message: str | None
    item_root_dir: str
    summary_out: str
    is_retry_candidate: bool


@dataclass(slots=True, frozen=True)
class BatchRunSummaryView:
    contract_version: int
    run_id: str
    retry_of_run_id: str | None
    generated_at_utc: str
    output_root_dir: str
    run_root_dir: str
    total_items: int
    queued_count: int
    running_count: int
    succeeded_count: int
    failed_count: int
    canceled_count: int
    skipped_count: int
    retryable_failed_count: int
    items: list[BatchSummaryViewItem]
    project_key: str | None = None
    project_root_dir: str | None = None
    project_manifest_file: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class BatchRunHistoryEntry:
    run_id: str
    run_root_dir: str
    generated_at_utc: str
    total_items: int
    succeeded_count: int
    failed_count: int
    canceled_count: int
    summary_file: str
    plan_file: str | None
    project_key: str | None = None
    project_root_dir: str | None = None
    project_manifest_file: str | None = None


@dataclass(slots=True, frozen=True)
class ProjectWorkspaceLayout:
    output_root_dir: str
    projects_root_dir: str
    project_key: str
    project_root_dir: str
    manifest_file: str
    artifacts_root_dir: str
    frontend_artifacts_dir: str
    api_artifacts_dir: str
    reports_dir: str
    runs_reports_dir: str
    consolidation_reports_dir: str
    coverage_ledger_file: str
    preview_workspace_dir: str


@dataclass(slots=True, frozen=True)
class ProjectRunRecord:
    run_id: str
    run_root_dir: str
    summary_file: str
    generated_at_utc: str
    total_items: int
    succeeded_count: int
    failed_count: int
    canceled_count: int
    retry_of_run_id: str | None
    consolidation_report_file: str | None


@dataclass(slots=True, frozen=True)
class ProjectCollisionRecord:
    detected_at_utc: str
    run_id: str
    category: str
    source_file: str
    target_file: str
    resolved_file: str


@dataclass(slots=True, frozen=True)
class ProjectManifest:
    contract_version: int
    project_key: str
    output_root_dir: str
    project_root_dir: str
    created_at_utc: str
    updated_at_utc: str
    run_count: int
    latest_run_id: str | None
    last_consolidation_report: str | None
    last_coverage_ledger_file: str | None = None
    runs: list[ProjectRunRecord] = field(default_factory=list)
    recent_collisions: list[ProjectCollisionRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class ProjectConsolidationFileOperation:
    category: str
    source_file: str
    target_file: str
    status: str
    note: str | None = None


@dataclass(slots=True, frozen=True)
class ProjectConsolidationReport:
    contract_version: int
    generated_at_utc: str
    project_key: str
    run_id: str
    output_root_dir: str
    project_root_dir: str
    project_manifest_file: str
    consolidation_report_file: str
    copied_count: int
    skipped_identical_count: int
    collision_renamed_count: int
    missing_source_count: int
    warning_count: int
    coverage_ledger_file: str | None = None
    coverage_ledger_totals: dict[str, int] = field(default_factory=dict)
    operations: list[ProjectConsolidationFileOperation] = field(default_factory=list)
    collisions: list[ProjectCollisionRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class ProjectCoverageLedgerRunSummary:
    run_id: str
    generated_at_utc: str
    total_items: int
    parse_total_nodes: int
    parse_unknown_tag_count: int
    parse_unknown_attr_count: int
    ui_total_nodes: int
    ui_rendered_nodes: int
    ui_unsupported_event_bindings: int
    ui_unsupported_tag_warning_count: int


@dataclass(slots=True, frozen=True)
class ProjectCoverageLedger:
    contract_version: int
    generated_at_utc: str
    project_key: str
    output_root_dir: str
    project_root_dir: str
    total_runs: int
    total_items: int
    parse_total_nodes: int
    parse_unknown_tag_count: int
    parse_unknown_attr_count: int
    ui_total_nodes: int
    ui_rendered_nodes: int
    ui_unsupported_event_bindings: int
    ui_unsupported_tag_warning_count: int
    unique_unknown_tags: list[str] = field(default_factory=list)
    unique_unknown_attrs: list[str] = field(default_factory=list)
    unique_ui_unsupported_tags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    runs: list[ProjectCoverageLedgerRunSummary] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_source_xml_queue(
    *,
    source_xml_file: str | Path | None = None,
    source_xml_dir: str | Path | None = None,
    recursive: bool = True,
    glob_pattern: str = DEFAULT_XML_GLOB_PATTERN,
    allow_empty: bool = False,
) -> list[Path]:
    has_source_file = source_xml_file is not None and str(source_xml_file).strip() != ""
    has_source_dir = source_xml_dir is not None and str(source_xml_dir).strip() != ""
    if has_source_file == has_source_dir:
        raise ValueError("Exactly one of `source_xml_file` or `source_xml_dir` must be provided.")

    if has_source_file:
        xml_file = _normalize_abs_path(str(source_xml_file).strip())
        if not xml_file.exists() or not xml_file.is_file():
            raise FileNotFoundError(f"Source XML file not found: {xml_file}")
        return [xml_file]

    source_dir = _normalize_abs_path(str(source_xml_dir).strip())
    if not source_dir.exists() or not source_dir.is_dir():
        raise FileNotFoundError(f"Source XML directory not found: {source_dir}")

    pattern = _normalize_glob_pattern(glob_pattern)
    matched = source_dir.rglob(pattern) if recursive else source_dir.glob(pattern)
    queue = sorted(
        (candidate.resolve() for candidate in matched if candidate.is_file()),
        key=lambda item: str(item).casefold(),
    )
    if not queue and not allow_empty:
        raise FileNotFoundError(
            f"No source XML files resolved from {source_dir} "
            f"(recursive={recursive}, glob_pattern={pattern!r})."
        )
    return queue


def resolve_project_key(
    output_root_dir: str | Path,
    *,
    project_key: str | None = None,
) -> str:
    if project_key is not None and project_key.strip():
        return _sanitize_token(project_key, fallback="project")
    output_root = _normalize_abs_path(output_root_dir)
    return _sanitize_token(output_root.name, fallback="project")


def build_project_workspace_layout(
    output_root_dir: str | Path,
    *,
    project_key: str | None = None,
) -> ProjectWorkspaceLayout:
    output_root = _normalize_abs_path(output_root_dir)
    resolved_project_key = resolve_project_key(output_root, project_key=project_key)
    projects_root = output_root / DEFAULT_PROJECTS_DIRNAME
    project_root = projects_root / resolved_project_key
    artifacts_root = project_root / "artifacts"
    reports_root = project_root / "reports"
    return ProjectWorkspaceLayout(
        output_root_dir=str(output_root),
        projects_root_dir=str(projects_root),
        project_key=resolved_project_key,
        project_root_dir=str(project_root),
        manifest_file=str(project_root / PROJECT_MANIFEST_FILENAME),
        artifacts_root_dir=str(artifacts_root),
        frontend_artifacts_dir=str(artifacts_root / "frontend"),
        api_artifacts_dir=str(artifacts_root / "api"),
        reports_dir=str(reports_root),
        runs_reports_dir=str(reports_root / "runs"),
        consolidation_reports_dir=str(reports_root / "project-consolidation"),
        coverage_ledger_file=str(project_root / COVERAGE_LEDGER_FILENAME),
        preview_workspace_dir=str(project_root / "preview-workspace"),
    )


def build_batch_output_layout(
    output_root_dir: str | Path,
    *,
    run_id: str,
    project_key: str | None = None,
) -> BatchOutputLayout:
    output_root = _normalize_abs_path(output_root_dir)
    sanitized_run_id = _sanitize_token(run_id, fallback="run")
    runs_root = output_root / DEFAULT_DESKTOP_RUNS_DIRNAME
    run_root = runs_root / sanitized_run_id
    project_layout = build_project_workspace_layout(output_root, project_key=project_key)
    return BatchOutputLayout(
        output_root_dir=str(output_root),
        runs_root_dir=str(runs_root),
        run_id=sanitized_run_id,
        run_root_dir=str(run_root),
        plan_file=str(run_root / "batch-run-plan.json"),
        summary_file=str(run_root / "batch-run-summary.json"),
        project_key=project_layout.project_key,
        project_root_dir=project_layout.project_root_dir,
        project_manifest_file=project_layout.manifest_file,
    )


def build_batch_run_plan(
    *,
    output_root_dir: str | Path,
    project_key: str | None = None,
    source_xml_file: str | Path | None = None,
    source_xml_dir: str | Path | None = None,
    recursive: bool = True,
    glob_pattern: str = DEFAULT_XML_GLOB_PATTERN,
    run_id: str | None = None,
    generated_at_utc: str | None = None,
) -> BatchRunPlan:
    xml_queue = resolve_source_xml_queue(
        source_xml_file=source_xml_file,
        source_xml_dir=source_xml_dir,
        recursive=recursive,
        glob_pattern=glob_pattern,
        allow_empty=False,
    )
    source_dir = _normalize_abs_path(source_xml_dir) if source_xml_dir is not None else None
    source_mode: BatchSourceMode = "folder" if source_dir is not None else "single_file"
    return _build_batch_run_plan_from_queue(
        xml_queue=xml_queue,
        output_root_dir=output_root_dir,
        source_mode=source_mode,
        source_xml_file=_normalize_abs_path(source_xml_file) if source_xml_file is not None else None,
        source_xml_dir=source_dir,
        recursive=recursive,
        glob_pattern=glob_pattern,
        run_id=run_id,
        generated_at_utc=generated_at_utc,
        retry_of_run_id=None,
        project_key=project_key,
    )


def build_batch_run_plan_from_xml_queue(
    *,
    xml_queue: Sequence[str | Path],
    output_root_dir: str | Path,
    project_key: str | None = None,
    run_id: str | None = None,
    generated_at_utc: str | None = None,
    retry_of_run_id: str | None = None,
) -> BatchRunPlan:
    return _build_batch_run_plan_from_queue(
        xml_queue=xml_queue,
        output_root_dir=output_root_dir,
        source_mode="explicit_queue",
        source_xml_file=None,
        source_xml_dir=None,
        recursive=False,
        glob_pattern=DEFAULT_XML_GLOB_PATTERN,
        run_id=run_id,
        generated_at_utc=generated_at_utc,
        retry_of_run_id=retry_of_run_id,
        project_key=project_key,
    )


def _build_batch_run_plan_from_queue(
    *,
    xml_queue: Sequence[str | Path],
    output_root_dir: str | Path,
    project_key: str | None,
    source_mode: BatchSourceMode,
    source_xml_file: Path | None,
    source_xml_dir: Path | None,
    recursive: bool,
    glob_pattern: str,
    run_id: str | None,
    generated_at_utc: str | None,
    retry_of_run_id: str | None,
) -> BatchRunPlan:
    if not xml_queue:
        raise ValueError("`xml_queue` must contain at least one XML file path.")

    normalized_queue: list[Path] = []
    seen: set[str] = set()
    for raw_path in xml_queue:
        candidate = _normalize_abs_path(raw_path)
        if not candidate.exists() or not candidate.is_file():
            raise FileNotFoundError(f"Batch queue XML file not found: {candidate}")
        marker = str(candidate)
        if marker in seen:
            continue
        normalized_queue.append(candidate)
        seen.add(marker)

    if not normalized_queue:
        raise ValueError("`xml_queue` resolved to an empty set after deduplication.")

    created_at = generated_at_utc or _utc_now_iso()
    resolved_run_id = run_id
    if resolved_run_id is None:
        prefix = _DEFAULT_RETRY_RUN_ID_PREFIX if retry_of_run_id else _DEFAULT_RUN_ID_PREFIX
        resolved_run_id = build_batch_run_id(
            normalized_queue,
            generated_at_utc=created_at,
            prefix=prefix,
        )

    layout = build_batch_output_layout(
        output_root_dir,
        run_id=resolved_run_id,
        project_key=project_key,
    )

    source_dir_for_relative = source_xml_dir
    pattern = _normalize_glob_pattern(glob_pattern)
    items: list[BatchRunPlanItem] = []
    for index, xml_path in enumerate(normalized_queue, start=1):
        stem = _sanitize_token(xml_path.stem, fallback="screen")
        path_digest = _hash_text(str(xml_path), length=12)
        item_key = f"{index:04d}-{stem}-{path_digest[:8]}"
        item_root = Path(layout.run_root_dir) / "items" / item_key
        out_dir = item_root / "e2e"
        api_out_dir = item_root / "generated-api"
        ui_out_dir = item_root / "generated-ui"
        preview_host_dir = item_root / "preview-host"
        summary_out = out_dir / f"{stem}.migration-summary.json"

        source_relative_path: str | None = None
        if source_dir_for_relative is not None:
            try:
                source_relative_path = str(xml_path.relative_to(source_dir_for_relative))
            except ValueError:
                source_relative_path = None

        items.append(
            BatchRunPlanItem(
                queue_index=index,
                xml_path=str(xml_path),
                xml_stem=stem,
                source_relative_path=source_relative_path,
                path_digest=path_digest,
                output=BatchRunItemLayout(
                    queue_index=index,
                    item_key=item_key,
                    item_root_dir=str(item_root),
                    out_dir=str(out_dir),
                    api_out_dir=str(api_out_dir),
                    ui_out_dir=str(ui_out_dir),
                    preview_host_dir=str(preview_host_dir),
                    summary_out=str(summary_out),
                ),
            )
        )

    selection = BatchSourceSelection(
        source_mode=source_mode,
        source_xml_file=str(source_xml_file) if source_xml_file is not None else None,
        source_xml_dir=str(source_xml_dir) if source_xml_dir is not None else None,
        recursive=recursive,
        glob_pattern=pattern,
    )
    summary = BatchRunPlanSummary(
        generated_at_utc=created_at,
        total_items=len(items),
        source_mode=source_mode,
        recursive=recursive,
        glob_pattern=pattern,
        queue_fingerprint=_build_queue_fingerprint(normalized_queue),
    )
    return BatchRunPlan(
        contract_version=BATCH_SUMMARY_CONTRACT_VERSION,
        run_id=layout.run_id,
        retry_of_run_id=retry_of_run_id,
        selection=selection,
        output=layout,
        items=items,
        summary=summary,
    )


def build_batch_summary_view(
    plan: BatchRunPlan,
    *,
    item_results: Sequence[BatchRunItemResult] | None = None,
    generated_at_utc: str | None = None,
) -> BatchRunSummaryView:
    by_index: dict[int, BatchRunItemResult] = {}
    by_path: dict[str, BatchRunItemResult] = {}
    for result in item_results or []:
        by_index[result.queue_index] = result
        by_path[str(_normalize_abs_path(result.xml_path))] = result

    items: list[BatchSummaryViewItem] = []
    counts: Counter[str] = Counter()
    for item in plan.items:
        normalized_path = str(_normalize_abs_path(item.xml_path))
        result = by_index.get(item.queue_index) or by_path.get(normalized_path)
        status: BatchItemStatus = result.status if result is not None else "queued"
        counts[status] += 1
        summary_file = (
            result.summary_file
            if result is not None and result.summary_file is not None
            else (item.output.summary_out if status in {"succeeded", "failed"} else None)
        )
        items.append(
            BatchSummaryViewItem(
                queue_index=item.queue_index,
                xml_path=item.xml_path,
                xml_stem=item.xml_stem,
                status=status,
                exit_code=result.exit_code if result is not None else None,
                summary_file=summary_file,
                error_message=result.error_message if result is not None else None,
                item_root_dir=item.output.item_root_dir,
                summary_out=item.output.summary_out,
                is_retry_candidate=status == "failed",
            )
        )

    produced_at = generated_at_utc or _utc_now_iso()
    return BatchRunSummaryView(
        contract_version=plan.contract_version,
        run_id=plan.run_id,
        retry_of_run_id=plan.retry_of_run_id,
        generated_at_utc=produced_at,
        output_root_dir=plan.output.output_root_dir,
        run_root_dir=plan.output.run_root_dir,
        total_items=len(items),
        queued_count=counts["queued"],
        running_count=counts["running"],
        succeeded_count=counts["succeeded"],
        failed_count=counts["failed"],
        canceled_count=counts["canceled"],
        skipped_count=counts["skipped"],
        retryable_failed_count=counts["failed"],
        items=items,
        project_key=plan.output.project_key,
        project_root_dir=plan.output.project_root_dir,
        project_manifest_file=plan.output.project_manifest_file,
    )


def build_failure_retry_plan(
    summary_view: BatchRunSummaryView,
    *,
    output_root_dir: str | Path | None = None,
    run_id: str | None = None,
    generated_at_utc: str | None = None,
) -> BatchRunPlan:
    failed_queue = [item.xml_path for item in summary_view.items if item.is_retry_candidate]
    if not failed_queue:
        raise ValueError("Failure-only retry plan requested but no failed items were found.")
    return build_batch_run_plan_from_xml_queue(
        xml_queue=failed_queue,
        output_root_dir=output_root_dir or summary_view.output_root_dir,
        project_key=summary_view.project_key,
        run_id=run_id,
        generated_at_utc=generated_at_utc,
        retry_of_run_id=summary_view.run_id,
    )


def write_batch_run_plan(
    plan: BatchRunPlan,
    *,
    output_path: str | Path | None = None,
    pretty: bool = True,
) -> Path:
    target = _normalize_abs_path(output_path) if output_path is not None else Path(plan.output.plan_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(plan.to_dict(), ensure_ascii=False, indent=2 if pretty else None),
        encoding="utf-8",
    )
    return target


def write_batch_summary_view(
    summary_view: BatchRunSummaryView,
    *,
    output_path: str | Path | None = None,
    pretty: bool = True,
) -> Path:
    target = (
        _normalize_abs_path(output_path)
        if output_path is not None
        else (_normalize_abs_path(summary_view.run_root_dir) / "batch-run-summary.json")
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(summary_view.to_dict(), ensure_ascii=False, indent=2 if pretty else None),
        encoding="utf-8",
    )
    return target


def _resolve_contract_file(
    path_or_run_root: str | Path,
    *,
    contract_filename: str,
) -> Path:
    candidate = _normalize_abs_path(path_or_run_root)
    if candidate.exists() and candidate.is_dir():
        return candidate / contract_filename
    return candidate


def _load_contract_json(
    path_or_run_root: str | Path,
    *,
    contract_filename: str,
    contract_name: str,
) -> tuple[dict[str, Any], Path]:
    target = _resolve_contract_file(path_or_run_root, contract_filename=contract_filename)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"{contract_name} not found: {target}")
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{contract_name} must be a JSON object: {target}")
    return payload, target


def _require_contract_mapping(
    payload: dict[str, Any],
    *,
    key: str,
    contract_name: str,
) -> dict[str, Any]:
    value = payload.get(key)
    if isinstance(value, dict):
        return value
    raise ValueError(f"{contract_name} must contain object field `{key}`.")


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    raise ValueError(f"Expected string or null, received: {type(value).__name__}")


def _required_str(
    payload: dict[str, Any],
    *,
    key: str,
    contract_name: str,
) -> str:
    value = payload.get(key)
    normalized = _optional_str(value)
    if normalized is None:
        raise ValueError(f"{contract_name} must contain non-empty string field `{key}`.")
    return normalized


def _required_int(
    payload: dict[str, Any],
    *,
    key: str,
    contract_name: str,
) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{contract_name} must contain integer field `{key}`.")
    return value


def read_batch_run_plan(path_or_run_root: str | Path) -> BatchRunPlan:
    payload, _ = _load_contract_json(
        path_or_run_root,
        contract_filename="batch-run-plan.json",
        contract_name="batch run plan",
    )
    contract_name = "batch run plan"
    selection_payload = _require_contract_mapping(
        payload,
        key="selection",
        contract_name=contract_name,
    )
    output_payload = _require_contract_mapping(
        payload,
        key="output",
        contract_name=contract_name,
    )
    summary_payload = _require_contract_mapping(
        payload,
        key="summary",
        contract_name=contract_name,
    )
    items_payload = payload.get("items")
    if not isinstance(items_payload, list):
        raise ValueError("batch run plan must contain array field `items`.")

    items: list[BatchRunPlanItem] = []
    for item_payload in items_payload:
        if not isinstance(item_payload, dict):
            raise ValueError("batch run plan `items` must contain JSON objects.")
        item_output_payload = _require_contract_mapping(
            item_payload,
            key="output",
            contract_name="batch run plan item",
        )
        items.append(
            BatchRunPlanItem(
                queue_index=_required_int(
                    item_payload,
                    key="queue_index",
                    contract_name="batch run plan item",
                ),
                xml_path=_required_str(
                    item_payload,
                    key="xml_path",
                    contract_name="batch run plan item",
                ),
                xml_stem=_required_str(
                    item_payload,
                    key="xml_stem",
                    contract_name="batch run plan item",
                ),
                source_relative_path=_optional_str(item_payload.get("source_relative_path")),
                path_digest=_required_str(
                    item_payload,
                    key="path_digest",
                    contract_name="batch run plan item",
                ),
                output=BatchRunItemLayout(
                    queue_index=_required_int(
                        item_output_payload,
                        key="queue_index",
                        contract_name="batch run item output",
                    ),
                    item_key=_required_str(
                        item_output_payload,
                        key="item_key",
                        contract_name="batch run item output",
                    ),
                    item_root_dir=_required_str(
                        item_output_payload,
                        key="item_root_dir",
                        contract_name="batch run item output",
                    ),
                    out_dir=_required_str(
                        item_output_payload,
                        key="out_dir",
                        contract_name="batch run item output",
                    ),
                    api_out_dir=_required_str(
                        item_output_payload,
                        key="api_out_dir",
                        contract_name="batch run item output",
                    ),
                    ui_out_dir=_required_str(
                        item_output_payload,
                        key="ui_out_dir",
                        contract_name="batch run item output",
                    ),
                    preview_host_dir=_required_str(
                        item_output_payload,
                        key="preview_host_dir",
                        contract_name="batch run item output",
                    ),
                    summary_out=_required_str(
                        item_output_payload,
                        key="summary_out",
                        contract_name="batch run item output",
                    ),
                ),
            )
        )

    return BatchRunPlan(
        contract_version=_required_int(
            payload,
            key="contract_version",
            contract_name=contract_name,
        ),
        run_id=_required_str(
            payload,
            key="run_id",
            contract_name=contract_name,
        ),
        retry_of_run_id=_optional_str(payload.get("retry_of_run_id")),
        selection=BatchSourceSelection(
            source_mode=_required_str(
                selection_payload,
                key="source_mode",
                contract_name="batch run selection",
            ),  # type: ignore[arg-type]
            source_xml_file=_optional_str(selection_payload.get("source_xml_file")),
            source_xml_dir=_optional_str(selection_payload.get("source_xml_dir")),
            recursive=bool(selection_payload.get("recursive", False)),
            glob_pattern=_required_str(
                selection_payload,
                key="glob_pattern",
                contract_name="batch run selection",
            ),
        ),
        output=BatchOutputLayout(
            output_root_dir=_required_str(
                output_payload,
                key="output_root_dir",
                contract_name="batch run output",
            ),
            runs_root_dir=_required_str(
                output_payload,
                key="runs_root_dir",
                contract_name="batch run output",
            ),
            run_id=_required_str(
                output_payload,
                key="run_id",
                contract_name="batch run output",
            ),
            run_root_dir=_required_str(
                output_payload,
                key="run_root_dir",
                contract_name="batch run output",
            ),
            plan_file=_required_str(
                output_payload,
                key="plan_file",
                contract_name="batch run output",
            ),
            summary_file=_required_str(
                output_payload,
                key="summary_file",
                contract_name="batch run output",
            ),
            project_key=_optional_str(output_payload.get("project_key")),
            project_root_dir=_optional_str(output_payload.get("project_root_dir")),
            project_manifest_file=_optional_str(output_payload.get("project_manifest_file")),
        ),
        items=items,
        summary=BatchRunPlanSummary(
            generated_at_utc=_required_str(
                summary_payload,
                key="generated_at_utc",
                contract_name="batch run summary metadata",
            ),
            total_items=_required_int(
                summary_payload,
                key="total_items",
                contract_name="batch run summary metadata",
            ),
            source_mode=_required_str(
                summary_payload,
                key="source_mode",
                contract_name="batch run summary metadata",
            ),  # type: ignore[arg-type]
            recursive=bool(summary_payload.get("recursive", False)),
            glob_pattern=_required_str(
                summary_payload,
                key="glob_pattern",
                contract_name="batch run summary metadata",
            ),
            queue_fingerprint=_required_str(
                summary_payload,
                key="queue_fingerprint",
                contract_name="batch run summary metadata",
            ),
        ),
    )


def read_batch_summary_view(path_or_run_root: str | Path) -> BatchRunSummaryView:
    payload, target = _load_contract_json(
        path_or_run_root,
        contract_filename="batch-run-summary.json",
        contract_name="batch run summary",
    )
    contract_name = "batch run summary"
    items_payload = payload.get("items")
    if not isinstance(items_payload, list):
        raise ValueError("batch run summary must contain array field `items`.")
    items: list[BatchSummaryViewItem] = []
    for item_payload in items_payload:
        if not isinstance(item_payload, dict):
            raise ValueError("batch run summary `items` must contain JSON objects.")
        items.append(
            BatchSummaryViewItem(
                queue_index=_required_int(
                    item_payload,
                    key="queue_index",
                    contract_name="batch run summary item",
                ),
                xml_path=_required_str(
                    item_payload,
                    key="xml_path",
                    contract_name="batch run summary item",
                ),
                xml_stem=_required_str(
                    item_payload,
                    key="xml_stem",
                    contract_name="batch run summary item",
                ),
                status=_required_str(
                    item_payload,
                    key="status",
                    contract_name="batch run summary item",
                ),  # type: ignore[arg-type]
                exit_code=item_payload.get("exit_code")
                if isinstance(item_payload.get("exit_code"), int)
                and not isinstance(item_payload.get("exit_code"), bool)
                else None,
                summary_file=_optional_str(item_payload.get("summary_file")),
                error_message=_optional_str(item_payload.get("error_message")),
                item_root_dir=_required_str(
                    item_payload,
                    key="item_root_dir",
                    contract_name="batch run summary item",
                ),
                summary_out=_required_str(
                    item_payload,
                    key="summary_out",
                    contract_name="batch run summary item",
                ),
                is_retry_candidate=bool(item_payload.get("is_retry_candidate", False)),
            )
        )

    try:
        run_root_dir = _required_str(payload, key="run_root_dir", contract_name=contract_name)
    except ValueError:
        run_root_dir = str(target.parent.resolve())

    return BatchRunSummaryView(
        contract_version=_required_int(payload, key="contract_version", contract_name=contract_name),
        run_id=_required_str(payload, key="run_id", contract_name=contract_name),
        retry_of_run_id=_optional_str(payload.get("retry_of_run_id")),
        generated_at_utc=_required_str(payload, key="generated_at_utc", contract_name=contract_name),
        output_root_dir=_required_str(payload, key="output_root_dir", contract_name=contract_name),
        run_root_dir=run_root_dir,
        total_items=_required_int(payload, key="total_items", contract_name=contract_name),
        queued_count=_required_int(payload, key="queued_count", contract_name=contract_name),
        running_count=_required_int(payload, key="running_count", contract_name=contract_name),
        succeeded_count=_required_int(payload, key="succeeded_count", contract_name=contract_name),
        failed_count=_required_int(payload, key="failed_count", contract_name=contract_name),
        canceled_count=_required_int(payload, key="canceled_count", contract_name=contract_name),
        skipped_count=_required_int(payload, key="skipped_count", contract_name=contract_name),
        retryable_failed_count=_required_int(
            payload,
            key="retryable_failed_count",
            contract_name=contract_name,
        ),
        items=items,
        project_key=_optional_str(payload.get("project_key")),
        project_root_dir=_optional_str(payload.get("project_root_dir")),
        project_manifest_file=_optional_str(payload.get("project_manifest_file")),
    )


def _parse_utc_sort_key(raw_utc: str) -> datetime:
    candidate = raw_utc.strip()
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _iter_history_run_roots(output_root: Path) -> list[tuple[Path, str | None, Path | None]]:
    run_roots: list[tuple[Path, str | None, Path | None]] = []
    legacy_runs_root = output_root / DEFAULT_DESKTOP_RUNS_DIRNAME
    if legacy_runs_root.exists() and legacy_runs_root.is_dir():
        for run_root in legacy_runs_root.iterdir():
            if run_root.is_dir():
                run_roots.append((run_root.resolve(), None, None))

    projects_root = output_root / DEFAULT_PROJECTS_DIRNAME
    if projects_root.exists() and projects_root.is_dir():
        for project_root in projects_root.iterdir():
            if not project_root.is_dir():
                continue
            runs_root = project_root / "runs"
            if not runs_root.exists() or not runs_root.is_dir():
                continue
            project_key = project_root.name
            for run_root in runs_root.iterdir():
                if run_root.is_dir():
                    run_roots.append((run_root.resolve(), project_key, project_root.resolve()))
    return run_roots


def list_batch_run_history(
    output_root_dir: str | Path,
    *,
    limit: int = 50,
) -> list[BatchRunHistoryEntry]:
    output_root = _normalize_abs_path(output_root_dir)
    run_roots = _iter_history_run_roots(output_root)
    if not run_roots:
        return []

    entries: list[BatchRunHistoryEntry] = []
    seen_roots: set[str] = set()
    for run_root, fallback_project_key, fallback_project_root in run_roots:
        marker = str(run_root)
        if marker in seen_roots:
            continue
        seen_roots.add(marker)
        summary_file = run_root / "batch-run-summary.json"
        if not summary_file.exists() or not summary_file.is_file():
            continue
        try:
            summary = read_batch_summary_view(summary_file)
        except Exception:
            continue

        plan_file = run_root / "batch-run-plan.json"
        entries.append(
            BatchRunHistoryEntry(
                run_id=summary.run_id,
                run_root_dir=str(run_root.resolve()),
                generated_at_utc=summary.generated_at_utc,
                total_items=summary.total_items,
                succeeded_count=summary.succeeded_count,
                failed_count=summary.failed_count,
                canceled_count=summary.canceled_count,
                summary_file=str(summary_file.resolve()),
                plan_file=str(plan_file.resolve()) if plan_file.exists() and plan_file.is_file() else None,
                project_key=summary.project_key or fallback_project_key,
                project_root_dir=summary.project_root_dir
                or (str(fallback_project_root) if fallback_project_root is not None else None),
                project_manifest_file=summary.project_manifest_file
                or (
                    str((fallback_project_root / PROJECT_MANIFEST_FILENAME).resolve())
                    if fallback_project_root is not None
                    else None
                ),
            )
        )

    entries.sort(key=lambda item: _parse_utc_sort_key(item.generated_at_utc), reverse=True)
    if limit > 0:
        return entries[:limit]
    return entries


def _iter_sorted_files(root_dir: Path) -> list[Path]:
    if not root_dir.exists() or not root_dir.is_dir():
        return []
    files = [path for path in root_dir.rglob("*") if path.is_file()]
    return sorted(files, key=lambda path: str(path).casefold())


def _files_are_identical(first: Path, second: Path) -> bool:
    if not first.exists() or not second.exists():
        return False
    if first.stat().st_size != second.stat().st_size:
        return False
    with first.open("rb") as first_stream, second.open("rb") as second_stream:
        while True:
            first_chunk = first_stream.read(65536)
            second_chunk = second_stream.read(65536)
            if first_chunk != second_chunk:
                return False
            if not first_chunk:
                return True


def _resolve_collision_target_path(target_file: Path, *, run_id: str) -> Path:
    run_token = _sanitize_token(run_id, fallback="run")
    stem = target_file.stem
    suffix = target_file.suffix
    candidate = target_file.with_name(f"{stem}__{run_token}{suffix}")
    sequence = 2
    while candidate.exists():
        candidate = target_file.with_name(f"{stem}__{run_token}_{sequence}{suffix}")
        sequence += 1
    return candidate


def _copy_file_with_conflict_resolution(
    source_file: Path,
    target_file: Path,
    *,
    run_id: str,
    category: str,
) -> tuple[str, Path, ProjectCollisionRecord | None]:
    target_file.parent.mkdir(parents=True, exist_ok=True)
    if not target_file.exists():
        shutil.copy2(source_file, target_file)
        return "copied", target_file, None
    if _files_are_identical(source_file, target_file):
        return "skipped_identical", target_file, None

    resolved_target = _resolve_collision_target_path(target_file, run_id=run_id)
    shutil.copy2(source_file, resolved_target)
    collision = ProjectCollisionRecord(
        detected_at_utc=_utc_now_iso(),
        run_id=run_id,
        category=category,
        source_file=str(source_file.resolve()),
        target_file=str(target_file.resolve()),
        resolved_file=str(resolved_target.resolve()),
    )
    return "collision_renamed", resolved_target, collision


def _parse_summary_reports_payload(summary_file: Path) -> dict[str, Any]:
    payload = json.loads(summary_file.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload
    return {}


def _safe_int(value: Any, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _resolve_report_file_from_summary(
    summary_payload: dict[str, Any],
    *,
    summary_file: Path,
    report_key: str,
) -> Path | None:
    reports_payload = summary_payload.get("reports")
    if not isinstance(reports_payload, dict):
        return None
    report_path = reports_payload.get(report_key)
    if not isinstance(report_path, str) or not report_path.strip():
        return None
    candidate = Path(report_path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (summary_file.parent / candidate).resolve()


def _extract_unsupported_tag_warnings(
    warnings_payload: Any,
) -> tuple[int, set[str]]:
    if not isinstance(warnings_payload, list):
        return 0, set()
    total = 0
    unsupported_tags: set[str] = set()
    for raw_warning in warnings_payload:
        if not isinstance(raw_warning, str):
            continue
        lowered = raw_warning.lower()
        marker = "unsupported tag:"
        marker_index = lowered.find(marker)
        if marker_index < 0:
            continue
        suffix = raw_warning[marker_index + len(marker) :].strip()
        if suffix:
            unsupported_tags.add(suffix)
        total += 1
    return total, unsupported_tags


def _collect_run_coverage_metrics(
    run: ProjectRunRecord,
) -> tuple[ProjectCoverageLedgerRunSummary, set[str], set[str], set[str], list[str]]:
    warnings: list[str] = []
    parse_total_nodes = 0
    parse_unknown_tag_count = 0
    parse_unknown_attr_count = 0
    ui_total_nodes = 0
    ui_rendered_nodes = 0
    ui_unsupported_event_bindings = 0
    ui_unsupported_tag_warning_count = 0
    unknown_tags: set[str] = set()
    unknown_attrs: set[str] = set()
    unsupported_ui_tags: set[str] = set()

    try:
        batch_summary = read_batch_summary_view(run.summary_file)
    except Exception as exc:
        warnings.append(
            "coverage_ledger: failed to parse batch summary for "
            f"run `{run.run_id}` ({run.summary_file}): {exc}"
        )
        batch_items: list[BatchSummaryViewItem] = []
    else:
        batch_items = batch_summary.items

    for batch_item in batch_items:
        migration_summary_path: Path | None = None
        if batch_item.summary_file is not None:
            migration_summary_path = _normalize_abs_path(batch_item.summary_file)
        else:
            migration_summary_path = _normalize_abs_path(batch_item.summary_out)
        if not migration_summary_path.exists() or not migration_summary_path.is_file():
            warnings.append(
                "coverage_ledger: migration summary missing for "
                f"run `{run.run_id}` queue_index={batch_item.queue_index} ({migration_summary_path})"
            )
            continue

        try:
            summary_payload = _parse_summary_reports_payload(migration_summary_path)
        except Exception as exc:
            warnings.append(
                "coverage_ledger: failed to parse migration summary for "
                f"run `{run.run_id}` queue_index={batch_item.queue_index} ({exc})"
            )
            continue

        stages_payload = summary_payload.get("stages")
        stage_ui_total_nodes = 0
        stage_ui_rendered_nodes = 0
        stage_ui_unsupported_event_bindings = 0
        if isinstance(stages_payload, dict):
            gen_ui_stage = stages_payload.get("gen_ui")
            if isinstance(gen_ui_stage, dict):
                stage_ui_total_nodes = _safe_int(gen_ui_stage.get("total_nodes"), default=0)
                stage_ui_rendered_nodes = _safe_int(gen_ui_stage.get("rendered_nodes"), default=0)
                stage_ui_unsupported_event_bindings = _safe_int(
                    gen_ui_stage.get("unsupported_event_bindings"),
                    default=0,
                )
                ui_total_nodes += stage_ui_total_nodes
                ui_rendered_nodes += stage_ui_rendered_nodes
                ui_unsupported_event_bindings += stage_ui_unsupported_event_bindings

        parse_report_file = _resolve_report_file_from_summary(
            summary_payload,
            summary_file=migration_summary_path,
            report_key="parse_report",
        )
        if parse_report_file is not None and parse_report_file.exists() and parse_report_file.is_file():
            try:
                parse_report_payload = json.loads(parse_report_file.read_text(encoding="utf-8"))
            except Exception as exc:
                warnings.append(
                    "coverage_ledger: failed to parse parse_report for "
                    f"run `{run.run_id}` ({parse_report_file}): {exc}"
                )
            else:
                if isinstance(parse_report_payload, dict):
                    stats_payload = parse_report_payload.get("stats")
                    if isinstance(stats_payload, dict):
                        parse_total_nodes += _safe_int(stats_payload.get("total_nodes"), default=0)
                        unknown_tags_payload = stats_payload.get("unknown_tags")
                        if isinstance(unknown_tags_payload, list):
                            parse_unknown_tag_count += len(unknown_tags_payload)
                            for item in unknown_tags_payload:
                                if not isinstance(item, dict):
                                    continue
                                tag = item.get("tag")
                                if isinstance(tag, str) and tag.strip():
                                    unknown_tags.add(tag.strip())
                        unknown_attrs_payload = stats_payload.get("unknown_attrs")
                        if isinstance(unknown_attrs_payload, list):
                            parse_unknown_attr_count += len(unknown_attrs_payload)
                            for item in unknown_attrs_payload:
                                if not isinstance(item, dict):
                                    continue
                                tag = item.get("tag")
                                attr = item.get("attr")
                                if (
                                    isinstance(tag, str)
                                    and tag.strip()
                                    and isinstance(attr, str)
                                    and attr.strip()
                                ):
                                    unknown_attrs.add(f"{tag.strip()}.{attr.strip()}")
        elif parse_report_file is not None:
            warnings.append(
                "coverage_ledger: parse_report missing for "
                f"run `{run.run_id}` ({parse_report_file})"
            )

        gen_ui_report_file = _resolve_report_file_from_summary(
            summary_payload,
            summary_file=migration_summary_path,
            report_key="gen_ui_report",
        )
        if gen_ui_report_file is not None and gen_ui_report_file.exists() and gen_ui_report_file.is_file():
            try:
                gen_ui_payload = json.loads(gen_ui_report_file.read_text(encoding="utf-8"))
            except Exception as exc:
                warnings.append(
                    "coverage_ledger: failed to parse gen_ui_report for "
                    f"run `{run.run_id}` ({gen_ui_report_file}): {exc}"
                )
            else:
                if isinstance(gen_ui_payload, dict):
                    summary_payload_ui = gen_ui_payload.get("summary")
                    if isinstance(summary_payload_ui, dict):
                        if stage_ui_total_nodes <= 0:
                            ui_total_nodes += _safe_int(summary_payload_ui.get("total_nodes"), default=0)
                        if stage_ui_rendered_nodes <= 0:
                            ui_rendered_nodes += _safe_int(summary_payload_ui.get("rendered_nodes"), default=0)
                        if stage_ui_unsupported_event_bindings <= 0:
                            ui_unsupported_event_bindings += _safe_int(
                                summary_payload_ui.get("unsupported_event_bindings"),
                                default=0,
                            )
                    unsupported_warning_count, unsupported_from_warnings = _extract_unsupported_tag_warnings(
                        gen_ui_payload.get("warnings")
                    )
                    ui_unsupported_tag_warning_count += unsupported_warning_count
                    unsupported_ui_tags.update(unsupported_from_warnings)
        elif gen_ui_report_file is not None:
            warnings.append(
                "coverage_ledger: gen_ui_report missing for "
                f"run `{run.run_id}` ({gen_ui_report_file})"
            )

    return (
        ProjectCoverageLedgerRunSummary(
            run_id=run.run_id,
            generated_at_utc=run.generated_at_utc,
            total_items=run.total_items,
            parse_total_nodes=parse_total_nodes,
            parse_unknown_tag_count=parse_unknown_tag_count,
            parse_unknown_attr_count=parse_unknown_attr_count,
            ui_total_nodes=ui_total_nodes,
            ui_rendered_nodes=ui_rendered_nodes,
            ui_unsupported_event_bindings=ui_unsupported_event_bindings,
            ui_unsupported_tag_warning_count=ui_unsupported_tag_warning_count,
        ),
        unknown_tags,
        unknown_attrs,
        unsupported_ui_tags,
        warnings,
    )


def build_project_coverage_ledger(
    layout: ProjectWorkspaceLayout,
    *,
    runs: Sequence[ProjectRunRecord],
    generated_at_utc: str | None = None,
) -> ProjectCoverageLedger:
    generated_at = generated_at_utc or _utc_now_iso()
    totals: Counter[str] = Counter()
    warnings: list[str] = []
    unknown_tags: set[str] = set()
    unknown_attrs: set[str] = set()
    unsupported_ui_tags: set[str] = set()
    run_summaries: list[ProjectCoverageLedgerRunSummary] = []

    for run in runs:
        run_summary, run_unknown_tags, run_unknown_attrs, run_unsupported_ui_tags, run_warnings = (
            _collect_run_coverage_metrics(run)
        )
        run_summaries.append(run_summary)
        totals["total_items"] += run_summary.total_items
        totals["parse_total_nodes"] += run_summary.parse_total_nodes
        totals["parse_unknown_tag_count"] += run_summary.parse_unknown_tag_count
        totals["parse_unknown_attr_count"] += run_summary.parse_unknown_attr_count
        totals["ui_total_nodes"] += run_summary.ui_total_nodes
        totals["ui_rendered_nodes"] += run_summary.ui_rendered_nodes
        totals["ui_unsupported_event_bindings"] += run_summary.ui_unsupported_event_bindings
        totals["ui_unsupported_tag_warning_count"] += run_summary.ui_unsupported_tag_warning_count
        unknown_tags.update(run_unknown_tags)
        unknown_attrs.update(run_unknown_attrs)
        unsupported_ui_tags.update(run_unsupported_ui_tags)
        warnings.extend(run_warnings)

    run_summaries.sort(key=lambda item: _parse_utc_sort_key(item.generated_at_utc), reverse=True)
    return ProjectCoverageLedger(
        contract_version=PROJECT_COVERAGE_LEDGER_CONTRACT_VERSION,
        generated_at_utc=generated_at,
        project_key=layout.project_key,
        output_root_dir=layout.output_root_dir,
        project_root_dir=layout.project_root_dir,
        total_runs=len(run_summaries),
        total_items=totals["total_items"],
        parse_total_nodes=totals["parse_total_nodes"],
        parse_unknown_tag_count=totals["parse_unknown_tag_count"],
        parse_unknown_attr_count=totals["parse_unknown_attr_count"],
        ui_total_nodes=totals["ui_total_nodes"],
        ui_rendered_nodes=totals["ui_rendered_nodes"],
        ui_unsupported_event_bindings=totals["ui_unsupported_event_bindings"],
        ui_unsupported_tag_warning_count=totals["ui_unsupported_tag_warning_count"],
        unique_unknown_tags=sorted(unknown_tags),
        unique_unknown_attrs=sorted(unknown_attrs),
        unique_ui_unsupported_tags=sorted(unsupported_ui_tags),
        warnings=warnings,
        runs=run_summaries,
    )


def write_project_coverage_ledger(
    ledger: ProjectCoverageLedger,
    *,
    output_path: str | Path | None = None,
    pretty: bool = True,
) -> Path:
    target = (
        _normalize_abs_path(output_path)
        if output_path is not None
        else (_normalize_abs_path(ledger.project_root_dir) / COVERAGE_LEDGER_FILENAME)
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(ledger.to_dict(), ensure_ascii=False, indent=2 if pretty else None),
        encoding="utf-8",
    )
    return target


def read_project_coverage_ledger(path_or_project_root: str | Path) -> ProjectCoverageLedger:
    payload, _ = _load_contract_json(
        path_or_project_root,
        contract_filename=COVERAGE_LEDGER_FILENAME,
        contract_name="project coverage ledger",
    )
    contract_name = "project coverage ledger"

    runs_payload = payload.get("runs", [])
    if not isinstance(runs_payload, list):
        raise ValueError("project coverage ledger must contain array field `runs`.")
    runs: list[ProjectCoverageLedgerRunSummary] = []
    for run_payload in runs_payload:
        if not isinstance(run_payload, dict):
            raise ValueError("project coverage ledger `runs` must contain JSON objects.")
        runs.append(
            ProjectCoverageLedgerRunSummary(
                run_id=_required_str(run_payload, key="run_id", contract_name="coverage run summary"),
                generated_at_utc=_required_str(
                    run_payload,
                    key="generated_at_utc",
                    contract_name="coverage run summary",
                ),
                total_items=_required_int(
                    run_payload,
                    key="total_items",
                    contract_name="coverage run summary",
                ),
                parse_total_nodes=_required_int(
                    run_payload,
                    key="parse_total_nodes",
                    contract_name="coverage run summary",
                ),
                parse_unknown_tag_count=_required_int(
                    run_payload,
                    key="parse_unknown_tag_count",
                    contract_name="coverage run summary",
                ),
                parse_unknown_attr_count=_required_int(
                    run_payload,
                    key="parse_unknown_attr_count",
                    contract_name="coverage run summary",
                ),
                ui_total_nodes=_required_int(
                    run_payload,
                    key="ui_total_nodes",
                    contract_name="coverage run summary",
                ),
                ui_rendered_nodes=_required_int(
                    run_payload,
                    key="ui_rendered_nodes",
                    contract_name="coverage run summary",
                ),
                ui_unsupported_event_bindings=_required_int(
                    run_payload,
                    key="ui_unsupported_event_bindings",
                    contract_name="coverage run summary",
                ),
                ui_unsupported_tag_warning_count=_required_int(
                    run_payload,
                    key="ui_unsupported_tag_warning_count",
                    contract_name="coverage run summary",
                ),
            )
        )

    def _optional_str_list(value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError(f"{contract_name} string-list field must be an array.")
        result: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError(f"{contract_name} string-list field must contain strings.")
            normalized = item.strip()
            if normalized:
                result.append(normalized)
        return result

    warnings_payload = payload.get("warnings", [])
    if not isinstance(warnings_payload, list):
        raise ValueError(f"{contract_name} field `warnings` must be an array.")
    warnings: list[str] = []
    for warning in warnings_payload:
        if not isinstance(warning, str):
            raise ValueError(f"{contract_name} field `warnings` must contain strings.")
        warnings.append(warning)

    return ProjectCoverageLedger(
        contract_version=_required_int(payload, key="contract_version", contract_name=contract_name),
        generated_at_utc=_required_str(payload, key="generated_at_utc", contract_name=contract_name),
        project_key=_required_str(payload, key="project_key", contract_name=contract_name),
        output_root_dir=_required_str(payload, key="output_root_dir", contract_name=contract_name),
        project_root_dir=_required_str(payload, key="project_root_dir", contract_name=contract_name),
        total_runs=_required_int(payload, key="total_runs", contract_name=contract_name),
        total_items=_required_int(payload, key="total_items", contract_name=contract_name),
        parse_total_nodes=_required_int(payload, key="parse_total_nodes", contract_name=contract_name),
        parse_unknown_tag_count=_required_int(
            payload,
            key="parse_unknown_tag_count",
            contract_name=contract_name,
        ),
        parse_unknown_attr_count=_required_int(
            payload,
            key="parse_unknown_attr_count",
            contract_name=contract_name,
        ),
        ui_total_nodes=_required_int(payload, key="ui_total_nodes", contract_name=contract_name),
        ui_rendered_nodes=_required_int(payload, key="ui_rendered_nodes", contract_name=contract_name),
        ui_unsupported_event_bindings=_required_int(
            payload,
            key="ui_unsupported_event_bindings",
            contract_name=contract_name,
        ),
        ui_unsupported_tag_warning_count=_required_int(
            payload,
            key="ui_unsupported_tag_warning_count",
            contract_name=contract_name,
        ),
        unique_unknown_tags=_optional_str_list(payload.get("unique_unknown_tags")),
        unique_unknown_attrs=_optional_str_list(payload.get("unique_unknown_attrs")),
        unique_ui_unsupported_tags=_optional_str_list(payload.get("unique_ui_unsupported_tags")),
        warnings=warnings,
        runs=runs,
    )


def _build_default_project_manifest(
    layout: ProjectWorkspaceLayout,
    *,
    generated_at_utc: str | None = None,
) -> ProjectManifest:
    created_at = generated_at_utc or _utc_now_iso()
    return ProjectManifest(
        contract_version=PROJECT_MANIFEST_CONTRACT_VERSION,
        project_key=layout.project_key,
        output_root_dir=layout.output_root_dir,
        project_root_dir=layout.project_root_dir,
        created_at_utc=created_at,
        updated_at_utc=created_at,
        run_count=0,
        latest_run_id=None,
        last_consolidation_report=None,
        last_coverage_ledger_file=None,
        runs=[],
        recent_collisions=[],
    )


def read_project_manifest(path_or_project_root: str | Path) -> ProjectManifest:
    payload, _ = _load_contract_json(
        path_or_project_root,
        contract_filename=PROJECT_MANIFEST_FILENAME,
        contract_name="project manifest",
    )
    contract_name = "project manifest"

    runs_payload = payload.get("runs", [])
    if not isinstance(runs_payload, list):
        raise ValueError("project manifest must contain array field `runs`.")

    runs: list[ProjectRunRecord] = []
    for run_payload in runs_payload:
        if not isinstance(run_payload, dict):
            raise ValueError("project manifest `runs` must contain JSON objects.")
        runs.append(
            ProjectRunRecord(
                run_id=_required_str(run_payload, key="run_id", contract_name="project run record"),
                run_root_dir=_required_str(
                    run_payload,
                    key="run_root_dir",
                    contract_name="project run record",
                ),
                summary_file=_required_str(
                    run_payload,
                    key="summary_file",
                    contract_name="project run record",
                ),
                generated_at_utc=_required_str(
                    run_payload,
                    key="generated_at_utc",
                    contract_name="project run record",
                ),
                total_items=_required_int(
                    run_payload,
                    key="total_items",
                    contract_name="project run record",
                ),
                succeeded_count=_required_int(
                    run_payload,
                    key="succeeded_count",
                    contract_name="project run record",
                ),
                failed_count=_required_int(
                    run_payload,
                    key="failed_count",
                    contract_name="project run record",
                ),
                canceled_count=_required_int(
                    run_payload,
                    key="canceled_count",
                    contract_name="project run record",
                ),
                retry_of_run_id=_optional_str(run_payload.get("retry_of_run_id")),
                consolidation_report_file=_optional_str(run_payload.get("consolidation_report_file")),
            )
        )

    collisions_payload = payload.get("recent_collisions", [])
    if not isinstance(collisions_payload, list):
        raise ValueError("project manifest `recent_collisions` must be an array.")
    recent_collisions: list[ProjectCollisionRecord] = []
    for collision_payload in collisions_payload:
        if not isinstance(collision_payload, dict):
            raise ValueError("project manifest `recent_collisions` must contain JSON objects.")
        recent_collisions.append(
            ProjectCollisionRecord(
                detected_at_utc=_required_str(
                    collision_payload,
                    key="detected_at_utc",
                    contract_name="project collision record",
                ),
                run_id=_required_str(
                    collision_payload,
                    key="run_id",
                    contract_name="project collision record",
                ),
                category=_required_str(
                    collision_payload,
                    key="category",
                    contract_name="project collision record",
                ),
                source_file=_required_str(
                    collision_payload,
                    key="source_file",
                    contract_name="project collision record",
                ),
                target_file=_required_str(
                    collision_payload,
                    key="target_file",
                    contract_name="project collision record",
                ),
                resolved_file=_required_str(
                    collision_payload,
                    key="resolved_file",
                    contract_name="project collision record",
                ),
            )
        )

    run_count_raw = payload.get("run_count")
    run_count = run_count_raw if isinstance(run_count_raw, int) and not isinstance(run_count_raw, bool) else len(runs)
    contract_version_raw = payload.get("contract_version")
    contract_version = (
        contract_version_raw
        if isinstance(contract_version_raw, int) and not isinstance(contract_version_raw, bool)
        else PROJECT_MANIFEST_CONTRACT_VERSION
    )
    return ProjectManifest(
        contract_version=contract_version,
        project_key=_required_str(payload, key="project_key", contract_name=contract_name),
        output_root_dir=_required_str(payload, key="output_root_dir", contract_name=contract_name),
        project_root_dir=_required_str(payload, key="project_root_dir", contract_name=contract_name),
        created_at_utc=_required_str(payload, key="created_at_utc", contract_name=contract_name),
        updated_at_utc=_required_str(payload, key="updated_at_utc", contract_name=contract_name),
        run_count=run_count,
        latest_run_id=_optional_str(payload.get("latest_run_id")),
        last_consolidation_report=_optional_str(payload.get("last_consolidation_report")),
        last_coverage_ledger_file=_optional_str(payload.get("last_coverage_ledger_file")),
        runs=runs,
        recent_collisions=recent_collisions,
    )


def write_project_manifest(
    manifest: ProjectManifest,
    *,
    output_path: str | Path | None = None,
    pretty: bool = True,
) -> Path:
    target = (
        _normalize_abs_path(output_path)
        if output_path is not None
        else (_normalize_abs_path(manifest.project_root_dir) / PROJECT_MANIFEST_FILENAME)
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2 if pretty else None),
        encoding="utf-8",
    )
    return target


def ensure_project_manifest(
    layout: ProjectWorkspaceLayout,
    *,
    pretty: bool = True,
) -> ProjectManifest:
    Path(layout.project_root_dir).mkdir(parents=True, exist_ok=True)
    Path(layout.frontend_artifacts_dir).mkdir(parents=True, exist_ok=True)
    Path(layout.api_artifacts_dir).mkdir(parents=True, exist_ok=True)
    Path(layout.reports_dir).mkdir(parents=True, exist_ok=True)
    Path(layout.runs_reports_dir).mkdir(parents=True, exist_ok=True)
    Path(layout.consolidation_reports_dir).mkdir(parents=True, exist_ok=True)
    Path(layout.preview_workspace_dir).mkdir(parents=True, exist_ok=True)

    manifest_path = Path(layout.manifest_file).resolve()
    if not manifest_path.exists() or not manifest_path.is_file():
        manifest = _build_default_project_manifest(layout)
        write_project_manifest(manifest, output_path=manifest_path, pretty=pretty)
        return manifest
    return read_project_manifest(manifest_path)


def _record_operation(
    operations: list[ProjectConsolidationFileOperation],
    *,
    category: str,
    source_file: Path,
    target_file: Path,
    status: str,
    note: str | None = None,
) -> None:
    operations.append(
        ProjectConsolidationFileOperation(
            category=category,
            source_file=str(source_file.resolve()),
            target_file=str(target_file.resolve()),
            status=status,
            note=note,
        )
    )


def _copy_tree_into_project(
    *,
    source_root: Path,
    destination_root: Path,
    run_id: str,
    category: str,
    operations: list[ProjectConsolidationFileOperation],
    collisions: list[ProjectCollisionRecord],
    warnings: list[str],
    counters: Counter[str],
) -> None:
    if not source_root.exists() or not source_root.is_dir():
        warnings.append(f"{category}: source directory not found ({source_root})")
        counters["missing_source"] += 1
        _record_operation(
            operations,
            category=category,
            source_file=source_root,
            target_file=destination_root,
            status="missing_source",
            note="source_directory_missing",
        )
        return

    for source_file in _iter_sorted_files(source_root):
        relative = source_file.relative_to(source_root)
        target_file = destination_root / relative
        status, resolved_target, collision = _copy_file_with_conflict_resolution(
            source_file,
            target_file,
            run_id=run_id,
            category=category,
        )
        counters[status] += 1
        note = None
        if collision is not None:
            collisions.append(collision)
            note = f"conflict_with={collision.target_file}"
        _record_operation(
            operations,
            category=category,
            source_file=source_file,
            target_file=resolved_target,
            status=status,
            note=note,
        )


def _resolve_summary_item_file(
    plan_item: BatchRunPlanItem,
    summary_view_by_index: dict[int, BatchSummaryViewItem],
) -> Path | None:
    summary_item = summary_view_by_index.get(plan_item.queue_index)
    if summary_item is not None and summary_item.summary_file is not None:
        return _normalize_abs_path(summary_item.summary_file)
    expected = _normalize_abs_path(plan_item.output.summary_out)
    if expected.exists() and expected.is_file():
        return expected
    return None


def consolidate_batch_run_artifacts(
    plan: BatchRunPlan,
    summary_view: BatchRunSummaryView,
    *,
    pretty: bool = True,
    project_key: str | None = None,
) -> ProjectConsolidationReport:
    output_root = _normalize_abs_path(plan.output.output_root_dir)
    effective_project_key = project_key or summary_view.project_key or plan.output.project_key
    project_layout = build_project_workspace_layout(output_root, project_key=effective_project_key)
    manifest = ensure_project_manifest(project_layout, pretty=pretty)

    generated_at = _utc_now_iso()
    warnings: list[str] = []
    operations: list[ProjectConsolidationFileOperation] = []
    collisions: list[ProjectCollisionRecord] = []
    counters: Counter[str] = Counter()
    summary_view_by_index = {item.queue_index: item for item in summary_view.items}
    run_id = summary_view.run_id

    frontend_root = Path(project_layout.frontend_artifacts_dir).resolve()
    api_root = Path(project_layout.api_artifacts_dir).resolve()
    run_reports_root = Path(project_layout.runs_reports_dir).resolve() / run_id / "items"

    for item in plan.items:
        ui_source_root = _normalize_abs_path(item.output.ui_out_dir) / "src"
        api_source_root = _normalize_abs_path(item.output.api_out_dir) / "src"
        _copy_tree_into_project(
            source_root=ui_source_root,
            destination_root=frontend_root / "src",
            run_id=run_id,
            category="frontend",
            operations=operations,
            collisions=collisions,
            warnings=warnings,
            counters=counters,
        )
        _copy_tree_into_project(
            source_root=api_source_root,
            destination_root=api_root / "src",
            run_id=run_id,
            category="api",
            operations=operations,
            collisions=collisions,
            warnings=warnings,
            counters=counters,
        )

        summary_file = _resolve_summary_item_file(item, summary_view_by_index)
        report_item_root = run_reports_root / item.output.item_key
        if summary_file is None or not summary_file.exists() or not summary_file.is_file():
            warnings.append(
                f"reports: summary file not found for queue_index={item.queue_index}"
            )
            counters["missing_source"] += 1
            _record_operation(
                operations,
                category="reports",
                source_file=_normalize_abs_path(item.output.summary_out),
                target_file=report_item_root / Path(item.output.summary_out).name,
                status="missing_source",
                note=f"queue_index={item.queue_index}",
            )
            continue

        summary_target = report_item_root / summary_file.name
        summary_status, summary_resolved_target, summary_collision = _copy_file_with_conflict_resolution(
            summary_file,
            summary_target,
            run_id=run_id,
            category="reports",
        )
        counters[summary_status] += 1
        summary_note = None
        if summary_collision is not None:
            collisions.append(summary_collision)
            summary_note = f"conflict_with={summary_collision.target_file}"
        _record_operation(
            operations,
            category="reports",
            source_file=summary_file,
            target_file=summary_resolved_target,
            status=summary_status,
            note=summary_note,
        )

        try:
            summary_payload = _parse_summary_reports_payload(summary_file)
        except Exception as exc:
            warnings.append(f"reports: failed to parse summary ({summary_file}): {exc}")
            continue

        reports_payload = summary_payload.get("reports")
        if not isinstance(reports_payload, dict):
            continue
        for report_name, report_path in sorted(reports_payload.items(), key=lambda pair: str(pair[0])):
            if not isinstance(report_path, str) or not report_path.strip():
                warnings.append(
                    "reports: invalid report path for "
                    f"`{report_name}` (queue_index={item.queue_index})"
                )
                continue
            source_candidate = Path(report_path).expanduser()
            source_file = (
                source_candidate.resolve()
                if source_candidate.is_absolute()
                else (summary_file.parent / source_candidate).resolve()
            )
            if not source_file.exists() or not source_file.is_file():
                warnings.append(
                    "reports: missing report file "
                    f"`{report_name}` for queue_index={item.queue_index} ({source_file})"
                )
                counters["missing_source"] += 1
                _record_operation(
                    operations,
                    category="reports",
                    source_file=source_file,
                    target_file=report_item_root / "reports" / source_file.name,
                    status="missing_source",
                    note=f"report_name={report_name}",
                )
                continue
            report_suffix = source_file.suffix or ".json"
            safe_report_name = _sanitize_token(str(report_name), fallback="report")
            target_file = report_item_root / "reports" / f"{safe_report_name}{report_suffix}"
            status, resolved_target, collision = _copy_file_with_conflict_resolution(
                source_file,
                target_file,
                run_id=run_id,
                category="reports",
            )
            counters[status] += 1
            report_note = f"report_name={report_name}"
            if collision is not None:
                collisions.append(collision)
                report_note = f"{report_note}; conflict_with={collision.target_file}"
            _record_operation(
                operations,
                category="reports",
                source_file=source_file,
                target_file=resolved_target,
                status=status,
                note=report_note,
            )

    consolidation_report_path = (
        Path(project_layout.consolidation_reports_dir).resolve() / f"{run_id}.consolidation.json"
    )
    run_record = ProjectRunRecord(
        run_id=summary_view.run_id,
        run_root_dir=summary_view.run_root_dir,
        summary_file=str(_normalize_abs_path(plan.output.summary_file)),
        generated_at_utc=summary_view.generated_at_utc,
        total_items=summary_view.total_items,
        succeeded_count=summary_view.succeeded_count,
        failed_count=summary_view.failed_count,
        canceled_count=summary_view.canceled_count,
        retry_of_run_id=summary_view.retry_of_run_id,
        consolidation_report_file=str(consolidation_report_path),
    )

    run_entries = [entry for entry in manifest.runs if entry.run_id != run_record.run_id]
    run_entries.append(run_record)
    run_entries.sort(key=lambda entry: _parse_utc_sort_key(entry.generated_at_utc), reverse=True)
    collision_history = [*manifest.recent_collisions, *collisions]
    if len(collision_history) > _PROJECT_COLLISION_HISTORY_LIMIT:
        collision_history = collision_history[-_PROJECT_COLLISION_HISTORY_LIMIT:]
    coverage_ledger = build_project_coverage_ledger(
        project_layout,
        runs=run_entries,
        generated_at_utc=generated_at,
    )
    coverage_ledger_path = write_project_coverage_ledger(coverage_ledger, pretty=pretty)
    warnings.extend(coverage_ledger.warnings)

    updated_manifest = ProjectManifest(
        contract_version=max(PROJECT_MANIFEST_CONTRACT_VERSION, manifest.contract_version),
        project_key=manifest.project_key,
        output_root_dir=manifest.output_root_dir,
        project_root_dir=manifest.project_root_dir,
        created_at_utc=manifest.created_at_utc,
        updated_at_utc=generated_at,
        run_count=len(run_entries),
        latest_run_id=run_entries[0].run_id if run_entries else None,
        last_consolidation_report=str(consolidation_report_path),
        last_coverage_ledger_file=str(coverage_ledger_path),
        runs=run_entries,
        recent_collisions=collision_history,
    )

    report = ProjectConsolidationReport(
        contract_version=PROJECT_CONSOLIDATION_CONTRACT_VERSION,
        generated_at_utc=generated_at,
        project_key=project_layout.project_key,
        run_id=run_id,
        output_root_dir=project_layout.output_root_dir,
        project_root_dir=project_layout.project_root_dir,
        project_manifest_file=project_layout.manifest_file,
        consolidation_report_file=str(consolidation_report_path),
        copied_count=counters["copied"],
        skipped_identical_count=counters["skipped_identical"],
        collision_renamed_count=counters["collision_renamed"],
        missing_source_count=counters["missing_source"],
        warning_count=len(warnings),
        coverage_ledger_file=str(coverage_ledger_path),
        coverage_ledger_totals={
            "total_runs": coverage_ledger.total_runs,
            "total_items": coverage_ledger.total_items,
            "parse_total_nodes": coverage_ledger.parse_total_nodes,
            "parse_unknown_tag_count": coverage_ledger.parse_unknown_tag_count,
            "parse_unknown_attr_count": coverage_ledger.parse_unknown_attr_count,
            "ui_total_nodes": coverage_ledger.ui_total_nodes,
            "ui_rendered_nodes": coverage_ledger.ui_rendered_nodes,
            "ui_unsupported_event_bindings": coverage_ledger.ui_unsupported_event_bindings,
            "ui_unsupported_tag_warning_count": coverage_ledger.ui_unsupported_tag_warning_count,
        },
        operations=operations,
        collisions=collisions,
        warnings=warnings,
    )
    consolidation_report_path.parent.mkdir(parents=True, exist_ok=True)
    consolidation_report_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2 if pretty else None),
        encoding="utf-8",
    )
    write_project_manifest(updated_manifest, pretty=pretty)
    return report


def materialize_batch_run_layout(
    plan: BatchRunPlan,
    *,
    write_plan_manifest: bool = True,
    write_queued_summary: bool = False,
    pretty: bool = True,
) -> Path:
    run_root = _normalize_abs_path(plan.output.run_root_dir)
    run_root.mkdir(parents=True, exist_ok=True)
    project_layout = build_project_workspace_layout(
        plan.output.output_root_dir,
        project_key=plan.output.project_key,
    )
    ensure_project_manifest(project_layout, pretty=pretty)
    for item in plan.items:
        Path(item.output.out_dir).mkdir(parents=True, exist_ok=True)
        Path(item.output.api_out_dir).mkdir(parents=True, exist_ok=True)
        Path(item.output.ui_out_dir).mkdir(parents=True, exist_ok=True)
        Path(item.output.preview_host_dir).mkdir(parents=True, exist_ok=True)

    if write_plan_manifest:
        write_batch_run_plan(plan, pretty=pretty)
    if write_queued_summary:
        summary_view = build_batch_summary_view(plan)
        write_batch_summary_view(summary_view, output_path=plan.output.summary_file, pretty=pretty)
    return run_root


__all__ = [
    "BATCH_SUMMARY_CONTRACT_VERSION",
    "COVERAGE_LEDGER_FILENAME",
    "DEFAULT_PROJECTS_DIRNAME",
    "PROJECT_COVERAGE_LEDGER_CONTRACT_VERSION",
    "PROJECT_CONSOLIDATION_CONTRACT_VERSION",
    "PROJECT_MANIFEST_CONTRACT_VERSION",
    "PROJECT_MANIFEST_FILENAME",
    "BatchItemStatus",
    "BatchOutputLayout",
    "BatchRunItemLayout",
    "BatchRunItemResult",
    "BatchRunHistoryEntry",
    "BatchRunPlan",
    "BatchRunPlanItem",
    "BatchRunPlanSummary",
    "BatchRunSummaryView",
    "BatchSourceMode",
    "BatchSourceSelection",
    "BatchSummaryViewItem",
    "DEFAULT_DESKTOP_RUNS_DIRNAME",
    "DEFAULT_XML_GLOB_PATTERN",
    "ProjectCollisionRecord",
    "ProjectCoverageLedger",
    "ProjectCoverageLedgerRunSummary",
    "ProjectConsolidationFileOperation",
    "ProjectConsolidationReport",
    "ProjectManifest",
    "ProjectRunRecord",
    "ProjectWorkspaceLayout",
    "build_batch_output_layout",
    "build_batch_run_id",
    "build_batch_run_plan",
    "build_batch_run_plan_from_xml_queue",
    "build_batch_summary_view",
    "build_project_coverage_ledger",
    "build_project_workspace_layout",
    "consolidate_batch_run_artifacts",
    "ensure_project_manifest",
    "build_failure_retry_plan",
    "list_batch_run_history",
    "materialize_batch_run_layout",
    "read_batch_run_plan",
    "read_batch_summary_view",
    "read_project_coverage_ledger",
    "read_project_manifest",
    "write_project_coverage_ledger",
    "resolve_source_xml_queue",
    "resolve_project_key",
    "write_project_manifest",
    "write_batch_run_plan",
    "write_batch_summary_view",
]
