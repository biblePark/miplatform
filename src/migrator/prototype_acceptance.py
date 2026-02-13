from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

UNRESOLVED_TRANSACTION_ADAPTER_SIGNAL = "UNIMPLEMENTED_TRANSACTION_ADAPTER"


def _to_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return int(text)
        except ValueError:
            return default
    return default


def _to_float(value: object, *, default: float) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return float(text)
        except ValueError:
            return default
    return default


def _to_optional_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text if text else None
    return str(value)


def _coverage_ratio(*, covered: int, total: int) -> float:
    if total <= 0:
        return 1.0
    return round(covered / total, 6)


def _load_json_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object payload: {path}")
    return payload


def _read_threshold_overrides(path: str | Path) -> dict[str, object]:
    payload = _load_json_object(Path(path).resolve())
    return payload


def _stage(payload: Mapping[str, object], name: str) -> dict[str, object]:
    stages = payload.get("stages")
    if not isinstance(stages, Mapping):
        return {}
    stage_payload = stages.get(name)
    if not isinstance(stage_payload, Mapping):
        return {}
    return dict(stage_payload)


def _resolve_summary_files(summary_artifact_paths: Sequence[str | Path]) -> list[Path]:
    if not summary_artifact_paths:
        raise FileNotFoundError("At least one migration summary artifact path is required.")

    resolved: set[Path] = set()
    missing_inputs: list[str] = []

    for raw_path in summary_artifact_paths:
        path = Path(raw_path).resolve()
        if path.is_file():
            resolved.add(path)
            continue
        if path.is_dir():
            for candidate in sorted(path.rglob("*.migration-summary.json")):
                if candidate.is_file():
                    resolved.add(candidate.resolve())
            continue
        missing_inputs.append(str(path))

    if missing_inputs:
        joined = ", ".join(sorted(missing_inputs))
        raise FileNotFoundError(f"Summary artifact path not found: {joined}")
    if not resolved:
        joined = ", ".join(sorted(str(Path(path).resolve()) for path in summary_artifact_paths))
        raise FileNotFoundError(
            "No migration summary artifacts found under inputs: "
            f"{joined}"
        )
    return sorted(resolved, key=lambda item: str(item))


def _resolve_behavior_actions_file(
    *,
    summary_file: Path,
    behavior_actions_file: str | None,
) -> Path | None:
    if behavior_actions_file is None:
        return None

    path = Path(behavior_actions_file)
    if path.is_absolute():
        return path.resolve()
    return (summary_file.parent / path).resolve()


def _count_unresolved_transaction_adapter_signals(
    *,
    transaction_count: int,
    behavior_actions_file: Path | None,
    warnings: list[str],
) -> int:
    if transaction_count <= 0:
        return 0
    if behavior_actions_file is None:
        warnings.append("gen_ui stage missing behavior_actions_file signal source.")
        return transaction_count
    if not behavior_actions_file.exists() or not behavior_actions_file.is_file():
        warnings.append(
            f"Behavior actions file is missing: {behavior_actions_file}"
        )
        return transaction_count
    try:
        text = behavior_actions_file.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - defensive path
        warnings.append(
            "Behavior actions file could not be read "
            f"({behavior_actions_file}): {exc}"
        )
        return transaction_count
    marker_count = text.count(UNRESOLVED_TRANSACTION_ADAPTER_SIGNAL)
    if marker_count <= 0:
        return 0
    return max(transaction_count, marker_count)


@dataclass(slots=True)
class PrototypeAcceptanceThresholds:
    max_failed_migration_count: int = 0
    max_fidelity_risk_count: int = 0
    min_event_runtime_wiring_coverage_ratio: float = 1.0
    max_unsupported_event_bindings: int = 0
    max_unresolved_transaction_adapter_signals: int = 0

    @classmethod
    def from_dict(
        cls,
        raw: Mapping[str, object] | None = None,
    ) -> "PrototypeAcceptanceThresholds":
        payload = raw if raw is not None else {}
        return cls(
            max_failed_migration_count=max(
                0,
                _to_int(payload.get("max_failed_migration_count"), default=0),
            ),
            max_fidelity_risk_count=max(
                0,
                _to_int(payload.get("max_fidelity_risk_count"), default=0),
            ),
            min_event_runtime_wiring_coverage_ratio=min(
                1.0,
                max(
                    0.0,
                    _to_float(
                        payload.get("min_event_runtime_wiring_coverage_ratio"),
                        default=1.0,
                    ),
                ),
            ),
            max_unsupported_event_bindings=max(
                0,
                _to_int(payload.get("max_unsupported_event_bindings"), default=0),
            ),
            max_unresolved_transaction_adapter_signals=max(
                0,
                _to_int(
                    payload.get("max_unresolved_transaction_adapter_signals"),
                    default=0,
                ),
            ),
        )


@dataclass(slots=True)
class PrototypeAcceptanceKpiResult:
    name: str
    comparator: str
    actual: int | float
    threshold: int | float
    passed: bool


@dataclass(slots=True)
class PrototypeAcceptanceTotals:
    total_migration_summaries: int
    total_transactions: int
    failed_migration_count: int
    fidelity_risk_count: int
    total_event_attributes: int
    runtime_wired_event_props: int
    event_runtime_wiring_coverage_ratio: float
    unsupported_event_bindings: int
    unresolved_transaction_adapter_signals: int


@dataclass(slots=True)
class PrototypeAcceptanceSummaryEvaluation:
    migration_summary_file: str
    screen_id: str | None
    overall_status: str | None
    total_transactions: int
    fidelity_risk_detected: bool
    missing_node_count: int
    position_style_nodes_with_risk: int
    total_event_attributes: int
    runtime_wired_event_props: int
    event_runtime_wiring_coverage_ratio: float
    unsupported_event_bindings: int
    behavior_actions_file: str | None
    unresolved_transaction_adapter_signals: int
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PrototypeAcceptanceReport:
    summary_files: list[str]
    thresholds: PrototypeAcceptanceThresholds
    totals: PrototypeAcceptanceTotals
    kpi_results: list[PrototypeAcceptanceKpiResult]
    verdict: str
    evaluations: list[PrototypeAcceptanceSummaryEvaluation]
    warnings: list[str] = field(default_factory=list)
    generated_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self, *, include_generated_at: bool = True) -> dict[str, Any]:
        payload = asdict(self)
        if not include_generated_at:
            payload.pop("generated_at_utc", None)
        return payload


def _evaluate_summary_file(summary_file: Path) -> PrototypeAcceptanceSummaryEvaluation:
    payload = _load_json_object(summary_file)
    warnings: list[str] = []

    fidelity_stage = _stage(payload, "fidelity_audit")
    missing_node_count = max(
        0,
        _to_int(fidelity_stage.get("missing_node_count"), default=0),
    )
    position_style_nodes_with_risk = max(
        0,
        _to_int(fidelity_stage.get("position_style_nodes_with_risk"), default=0),
    )
    risk_detected = bool(fidelity_stage.get("risk_detected"))
    fidelity_risk_detected = bool(
        risk_detected or missing_node_count > 0 or position_style_nodes_with_risk > 0
    )

    gen_ui_stage = _stage(payload, "gen_ui")
    total_event_attributes = max(
        0,
        _to_int(gen_ui_stage.get("total_event_attributes"), default=0),
    )
    runtime_wired_event_props = max(
        0,
        _to_int(gen_ui_stage.get("runtime_wired_event_props"), default=0),
    )
    unsupported_event_bindings = max(
        0,
        _to_int(gen_ui_stage.get("unsupported_event_bindings"), default=0),
    )
    coverage_ratio = _coverage_ratio(
        covered=runtime_wired_event_props,
        total=total_event_attributes,
    )

    map_api_stage = _stage(payload, "map_api")
    total_transactions = max(
        0,
        _to_int(map_api_stage.get("total_transactions"), default=0),
    )

    behavior_actions_file_raw = _to_optional_str(gen_ui_stage.get("behavior_actions_file"))
    resolved_behavior_actions_file = _resolve_behavior_actions_file(
        summary_file=summary_file,
        behavior_actions_file=behavior_actions_file_raw,
    )
    unresolved_transaction_adapter_signals = _count_unresolved_transaction_adapter_signals(
        transaction_count=total_transactions,
        behavior_actions_file=resolved_behavior_actions_file,
        warnings=warnings,
    )

    return PrototypeAcceptanceSummaryEvaluation(
        migration_summary_file=str(summary_file),
        screen_id=_to_optional_str(payload.get("screen_id")),
        overall_status=_to_optional_str(payload.get("overall_status")),
        total_transactions=total_transactions,
        fidelity_risk_detected=fidelity_risk_detected,
        missing_node_count=missing_node_count,
        position_style_nodes_with_risk=position_style_nodes_with_risk,
        total_event_attributes=total_event_attributes,
        runtime_wired_event_props=runtime_wired_event_props,
        event_runtime_wiring_coverage_ratio=coverage_ratio,
        unsupported_event_bindings=unsupported_event_bindings,
        behavior_actions_file=(
            str(resolved_behavior_actions_file)
            if resolved_behavior_actions_file is not None
            else None
        ),
        unresolved_transaction_adapter_signals=unresolved_transaction_adapter_signals,
        warnings=warnings,
    )


def _compute_totals(
    evaluations: Sequence[PrototypeAcceptanceSummaryEvaluation],
) -> PrototypeAcceptanceTotals:
    failed_migration_count = sum(
        1 for item in evaluations if item.overall_status != "success"
    )
    fidelity_risk_count = sum(
        1 for item in evaluations if item.fidelity_risk_detected
    )
    total_transactions = sum(item.total_transactions for item in evaluations)
    total_event_attributes = sum(item.total_event_attributes for item in evaluations)
    runtime_wired_event_props = sum(item.runtime_wired_event_props for item in evaluations)
    unsupported_event_bindings = sum(
        item.unsupported_event_bindings for item in evaluations
    )
    unresolved_transaction_adapter_signals = sum(
        item.unresolved_transaction_adapter_signals for item in evaluations
    )
    return PrototypeAcceptanceTotals(
        total_migration_summaries=len(evaluations),
        total_transactions=total_transactions,
        failed_migration_count=failed_migration_count,
        fidelity_risk_count=fidelity_risk_count,
        total_event_attributes=total_event_attributes,
        runtime_wired_event_props=runtime_wired_event_props,
        event_runtime_wiring_coverage_ratio=_coverage_ratio(
            covered=runtime_wired_event_props,
            total=total_event_attributes,
        ),
        unsupported_event_bindings=unsupported_event_bindings,
        unresolved_transaction_adapter_signals=unresolved_transaction_adapter_signals,
    )


def _build_kpi_results(
    *,
    totals: PrototypeAcceptanceTotals,
    thresholds: PrototypeAcceptanceThresholds,
) -> list[PrototypeAcceptanceKpiResult]:
    return [
        PrototypeAcceptanceKpiResult(
            name="failed_migration_count",
            comparator="<=",
            actual=totals.failed_migration_count,
            threshold=thresholds.max_failed_migration_count,
            passed=totals.failed_migration_count <= thresholds.max_failed_migration_count,
        ),
        PrototypeAcceptanceKpiResult(
            name="fidelity_risk_count",
            comparator="<=",
            actual=totals.fidelity_risk_count,
            threshold=thresholds.max_fidelity_risk_count,
            passed=totals.fidelity_risk_count <= thresholds.max_fidelity_risk_count,
        ),
        PrototypeAcceptanceKpiResult(
            name="event_runtime_wiring_coverage_ratio",
            comparator=">=",
            actual=totals.event_runtime_wiring_coverage_ratio,
            threshold=thresholds.min_event_runtime_wiring_coverage_ratio,
            passed=(
                totals.event_runtime_wiring_coverage_ratio
                >= thresholds.min_event_runtime_wiring_coverage_ratio
            ),
        ),
        PrototypeAcceptanceKpiResult(
            name="unsupported_event_bindings",
            comparator="<=",
            actual=totals.unsupported_event_bindings,
            threshold=thresholds.max_unsupported_event_bindings,
            passed=(
                totals.unsupported_event_bindings
                <= thresholds.max_unsupported_event_bindings
            ),
        ),
        PrototypeAcceptanceKpiResult(
            name="unresolved_transaction_adapter_signals",
            comparator="<=",
            actual=totals.unresolved_transaction_adapter_signals,
            threshold=thresholds.max_unresolved_transaction_adapter_signals,
            passed=(
                totals.unresolved_transaction_adapter_signals
                <= thresholds.max_unresolved_transaction_adapter_signals
            ),
        ),
    ]


def generate_prototype_acceptance_report(
    summary_artifact_paths: Sequence[str | Path],
    *,
    thresholds: PrototypeAcceptanceThresholds | None = None,
) -> PrototypeAcceptanceReport:
    resolved_thresholds = thresholds or PrototypeAcceptanceThresholds()
    summary_files = _resolve_summary_files(summary_artifact_paths)
    evaluations = [
        _evaluate_summary_file(summary_file)
        for summary_file in summary_files
    ]
    totals = _compute_totals(evaluations)
    kpi_results = _build_kpi_results(totals=totals, thresholds=resolved_thresholds)
    verdict = "pass" if all(item.passed for item in kpi_results) else "fail"
    warnings = [
        f"{evaluation.migration_summary_file}: {warning}"
        for evaluation in evaluations
        for warning in evaluation.warnings
    ]
    return PrototypeAcceptanceReport(
        summary_files=[str(path) for path in summary_files],
        thresholds=resolved_thresholds,
        totals=totals,
        kpi_results=kpi_results,
        verdict=verdict,
        evaluations=evaluations,
        warnings=warnings,
    )


def build_prototype_acceptance_thresholds(
    *,
    thresholds_file: str | Path | None = None,
    overrides: Mapping[str, object] | None = None,
) -> PrototypeAcceptanceThresholds:
    merged: dict[str, object] = {}
    if thresholds_file is not None:
        merged.update(_read_threshold_overrides(thresholds_file))
    if overrides is not None:
        merged.update(overrides)
    return PrototypeAcceptanceThresholds.from_dict(merged)


__all__ = [
    "PrototypeAcceptanceKpiResult",
    "PrototypeAcceptanceReport",
    "PrototypeAcceptanceSummaryEvaluation",
    "PrototypeAcceptanceThresholds",
    "PrototypeAcceptanceTotals",
    "build_prototype_acceptance_thresholds",
    "generate_prototype_acceptance_report",
]
