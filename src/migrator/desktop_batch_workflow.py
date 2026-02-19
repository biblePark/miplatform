from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Literal, Sequence

DEFAULT_XML_GLOB_PATTERN = "*.xml"
DEFAULT_DESKTOP_RUNS_DIRNAME = "desktop-runs"
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


def build_batch_output_layout(output_root_dir: str | Path, *, run_id: str) -> BatchOutputLayout:
    output_root = _normalize_abs_path(output_root_dir)
    sanitized_run_id = _sanitize_token(run_id, fallback="run")
    runs_root = output_root / DEFAULT_DESKTOP_RUNS_DIRNAME
    run_root = runs_root / sanitized_run_id
    return BatchOutputLayout(
        output_root_dir=str(output_root),
        runs_root_dir=str(runs_root),
        run_id=sanitized_run_id,
        run_root_dir=str(run_root),
        plan_file=str(run_root / "batch-run-plan.json"),
        summary_file=str(run_root / "batch-run-summary.json"),
    )


def build_batch_run_plan(
    *,
    output_root_dir: str | Path,
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
    )


def build_batch_run_plan_from_xml_queue(
    *,
    xml_queue: Sequence[str | Path],
    output_root_dir: str | Path,
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
    )


def _build_batch_run_plan_from_queue(
    *,
    xml_queue: Sequence[str | Path],
    output_root_dir: str | Path,
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

    layout = build_batch_output_layout(output_root_dir, run_id=resolved_run_id)

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


def materialize_batch_run_layout(
    plan: BatchRunPlan,
    *,
    write_plan_manifest: bool = True,
    write_queued_summary: bool = False,
    pretty: bool = True,
) -> Path:
    run_root = _normalize_abs_path(plan.output.run_root_dir)
    run_root.mkdir(parents=True, exist_ok=True)
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
    "BatchItemStatus",
    "BatchOutputLayout",
    "BatchRunItemLayout",
    "BatchRunItemResult",
    "BatchRunPlan",
    "BatchRunPlanItem",
    "BatchRunPlanSummary",
    "BatchRunSummaryView",
    "BatchSourceMode",
    "BatchSourceSelection",
    "BatchSummaryViewItem",
    "DEFAULT_DESKTOP_RUNS_DIRNAME",
    "DEFAULT_XML_GLOB_PATTERN",
    "build_batch_output_layout",
    "build_batch_run_id",
    "build_batch_run_plan",
    "build_batch_run_plan_from_xml_queue",
    "build_batch_summary_view",
    "build_failure_retry_plan",
    "materialize_batch_run_layout",
    "resolve_source_xml_queue",
    "write_batch_run_plan",
    "write_batch_summary_view",
]
