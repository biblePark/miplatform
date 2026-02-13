#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOLERANCES_PATH = ROOT / "ops" / "real_sample_baseline_tolerances.json"

STAGES = ("parse", "map_api", "gen_ui", "fidelity_audit", "sync_preview")
STAGE_STATUSES = ("success", "failure", "skipped", "pending", "missing")

LOWER_IS_BETTER_DEFAULTS = {
    "totals.failure_count": 0,
    "malformed_xml_blockers.count": 0,
    **{f"stage.{stage}.failure": 0 for stage in STAGES},
    "risk.extraction.files_with_risk": 0,
    "risk.extraction.gate_failure_total": 0,
    "risk.mapping.files_with_risk": 0,
    "risk.mapping.mapped_failure_total": 0,
    "risk.mapping.unsupported_total": 0,
    "risk.fidelity.files_with_risk": 0,
    "risk.fidelity.gate_failure_total": 0,
    "risk.fidelity.ui_fallback_warning_total": 0,
    "risk.fidelity.missing_node_total": 0,
    "risk.fidelity.position_style_nodes_with_risk_total": 0,
}
HIGHER_IS_BETTER_DEFAULTS = {
    "totals.success_count": 0,
}


def _load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_file(path: Path, payload: object, *, pretty: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            indent=2 if pretty else None,
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _normalize_round_id(value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("--round must be a non-empty string")
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", trimmed).strip("-_")
    return normalized or "round"


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _sample_paths_from_summary(summary: dict[str, Any]) -> list[str]:
    raw_samples = summary.get("samples", [])
    if not isinstance(raw_samples, list):
        return []
    paths = {
        str(item.get("xml_path"))
        for item in raw_samples
        if isinstance(item, dict) and isinstance(item.get("xml_path"), str)
    }
    return sorted(paths)


def _sample_paths_hash(paths: list[str]) -> str:
    materialized = "\n".join(paths)
    return hashlib.sha256(materialized.encode("utf-8")).hexdigest()


def _normalize_metric_map(raw_metrics: dict[str, Any]) -> dict[str, int]:
    return {
        str(metric): _safe_int(value)
        for metric, value in raw_metrics.items()
        if isinstance(metric, str)
    }


def _extract_kpis_from_summary(summary: dict[str, Any]) -> dict[str, int]:
    metrics: dict[str, int] = {}

    totals = summary.get("totals", {})
    if not isinstance(totals, dict):
        totals = {}
    metrics["totals.total_samples"] = _safe_int(totals.get("total_samples", 0))
    metrics["totals.success_count"] = _safe_int(totals.get("success_count", 0))
    metrics["totals.failure_count"] = _safe_int(totals.get("failure_count", 0))

    blockers = summary.get("malformed_xml_blockers", [])
    metrics["malformed_xml_blockers.count"] = len(blockers) if isinstance(blockers, list) else 0

    stage_status_counts = summary.get("stage_status_counts", {})
    if not isinstance(stage_status_counts, dict):
        stage_status_counts = {}

    for stage in STAGES:
        raw_stage_counts = stage_status_counts.get(stage, {})
        stage_counts = raw_stage_counts if isinstance(raw_stage_counts, dict) else {}
        for status in STAGE_STATUSES:
            metrics[f"stage.{stage}.{status}"] = _safe_int(stage_counts.get(status, 0))
        for status, value in stage_counts.items():
            if not isinstance(status, str):
                continue
            if status in STAGE_STATUSES:
                continue
            metrics[f"stage.{stage}.{status}"] = _safe_int(value)

    risk_trends = summary.get("risk_trends", {})
    if not isinstance(risk_trends, dict):
        risk_trends = {}

    extraction = risk_trends.get("extraction", {})
    if not isinstance(extraction, dict):
        extraction = {}
    extraction_gates = extraction.get("gate_failure_counts", {})
    if not isinstance(extraction_gates, dict):
        extraction_gates = {}
    metrics["risk.extraction.files_with_risk"] = _safe_int(extraction.get("files_with_risk", 0))
    metrics["risk.extraction.gate_failure_total"] = sum(
        _safe_int(count) for count in extraction_gates.values()
    )
    for gate_name in sorted(key for key in extraction_gates.keys() if isinstance(key, str)):
        metrics[f"risk.extraction.gate.{gate_name}"] = _safe_int(extraction_gates[gate_name])

    mapping = risk_trends.get("mapping", {})
    if not isinstance(mapping, dict):
        mapping = {}
    metrics["risk.mapping.files_with_risk"] = _safe_int(mapping.get("files_with_risk", 0))
    metrics["risk.mapping.mapped_failure_total"] = _safe_int(
        mapping.get("mapped_failure_total", 0)
    )
    metrics["risk.mapping.unsupported_total"] = _safe_int(mapping.get("unsupported_total", 0))

    fidelity = risk_trends.get("fidelity", {})
    if not isinstance(fidelity, dict):
        fidelity = {}
    fidelity_gates = fidelity.get("gate_failure_counts", {})
    if not isinstance(fidelity_gates, dict):
        fidelity_gates = {}
    metrics["risk.fidelity.files_with_risk"] = _safe_int(fidelity.get("files_with_risk", 0))
    metrics["risk.fidelity.gate_failure_total"] = sum(
        _safe_int(count) for count in fidelity_gates.values()
    )
    for gate_name in sorted(key for key in fidelity_gates.keys() if isinstance(key, str)):
        metrics[f"risk.fidelity.gate.{gate_name}"] = _safe_int(fidelity_gates[gate_name])
    metrics["risk.fidelity.ui_fallback_warning_total"] = _safe_int(
        fidelity.get("ui_fallback_warning_total", 0)
    )
    metrics["risk.fidelity.missing_node_total"] = _safe_int(
        fidelity.get("missing_node_total", 0)
    )
    metrics["risk.fidelity.position_style_nodes_with_risk_total"] = _safe_int(
        fidelity.get("position_style_nodes_with_risk_total", 0)
    )

    return dict(sorted(metrics.items()))


def _load_metrics_payload(path: Path) -> dict[str, Any]:
    payload = _load_json_file(path)
    if (
        payload.get("snapshot_type") == "real_sample_regression_baseline"
        and isinstance(payload.get("metrics"), dict)
    ):
        sample_set = payload.get("sample_set", {})
        sample_set_payload = sample_set if isinstance(sample_set, dict) else {}
        return {
            "kind": "baseline_snapshot",
            "metrics": _normalize_metric_map(payload["metrics"]),
            "round_id": payload.get("round_id"),
            "source_summary_json": payload.get("source_summary_json"),
            "sample_set": {
                "count": _safe_int(sample_set_payload.get("count", 0)),
                "sample_paths_sha256": str(
                    sample_set_payload.get("sample_paths_sha256", "")
                ),
            },
        }

    sample_paths = _sample_paths_from_summary(payload)
    return {
        "kind": "regression_summary",
        "metrics": _extract_kpis_from_summary(payload),
        "round_id": None,
        "source_summary_json": str(path),
        "sample_set": {
            "count": len(sample_paths),
            "sample_paths_sha256": _sample_paths_hash(sample_paths),
        },
    }


def _build_snapshot_payload(
    *,
    round_id: str,
    summary_json: Path,
    summary_payload: dict[str, Any],
) -> dict[str, Any]:
    sample_paths = _sample_paths_from_summary(summary_payload)
    return {
        "schema_version": 1,
        "snapshot_type": "real_sample_regression_baseline",
        "round_id": round_id,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_summary_json": str(summary_json.resolve()),
        "sample_set": {
            "count": len(sample_paths),
            "sample_paths_sha256": _sample_paths_hash(sample_paths),
            "sample_paths": sample_paths,
        },
        "metrics": _extract_kpis_from_summary(summary_payload),
    }


def _render_snapshot_markdown(snapshot: dict[str, Any]) -> str:
    metrics = snapshot.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}

    lines = [
        "# Real-Sample Baseline Snapshot",
        "",
        f"- Round: `{snapshot.get('round_id', 'unknown')}`",
        f"- Generated at (UTC): `{snapshot.get('generated_at_utc', 'unknown')}`",
        f"- Source summary: `{snapshot.get('source_summary_json', 'unknown')}`",
        f"- Sample count: `{snapshot.get('sample_set', {}).get('count', 0)}`",
        "- Sample paths hash (sha256): "
        f"`{snapshot.get('sample_set', {}).get('sample_paths_sha256', '')}`",
        "",
        "## Stage KPIs",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]

    for metric, value in sorted(metrics.items()):
        if not isinstance(metric, str):
            continue
        if not metric.startswith("stage."):
            continue
        lines.append(f"| `{metric}` | {int(value)} |")

    lines.extend([
        "",
        "## Risk Trend KPIs",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ])
    for metric, value in sorted(metrics.items()):
        if not isinstance(metric, str):
            continue
        if not metric.startswith("risk."):
            continue
        lines.append(f"| `{metric}` | {int(value)} |")

    lines.extend([
        "",
        "## Overall KPIs",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ])
    for metric, value in sorted(metrics.items()):
        if not isinstance(metric, str):
            continue
        if metric.startswith("stage.") or metric.startswith("risk."):
            continue
        lines.append(f"| `{metric}` | {int(value)} |")

    return "\n".join(lines) + "\n"


def _metric_direction(metric: str) -> str:
    if metric == "totals.total_samples":
        return "neutral"
    if metric == "totals.success_count" or metric.endswith(".success"):
        return "higher_is_better"
    return "lower_is_better"


def _metric_dimension(metric: str) -> tuple[str, str]:
    if metric.startswith("stage."):
        parts = metric.split(".")
        scope = parts[1] if len(parts) > 1 else "stage"
        return ("stage", scope)
    if metric.startswith("risk."):
        parts = metric.split(".")
        scope = parts[1] if len(parts) > 1 else "risk"
        return ("risk_trend", scope)
    if metric.startswith("totals."):
        return ("overall", "totals")
    if metric.startswith("malformed_xml_blockers."):
        return ("overall", "blockers")
    return ("overall", "misc")


def _build_diff_entries(
    *,
    baseline_metrics: dict[str, int],
    current_metrics: dict[str, int],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for metric in sorted(set(baseline_metrics) | set(current_metrics)):
        baseline_value = baseline_metrics.get(metric)
        current_value = current_metrics.get(metric)
        direction = _metric_direction(metric)
        dimension, scope = _metric_dimension(metric)

        if baseline_value is None:
            entries.append(
                {
                    "metric": metric,
                    "dimension": dimension,
                    "scope": scope,
                    "direction": direction,
                    "baseline": None,
                    "current": int(current_value),
                    "delta": None,
                    "movement": "new_metric",
                }
            )
            continue
        if current_value is None:
            entries.append(
                {
                    "metric": metric,
                    "dimension": dimension,
                    "scope": scope,
                    "direction": direction,
                    "baseline": int(baseline_value),
                    "current": None,
                    "delta": None,
                    "movement": "dropped_metric",
                }
            )
            continue

        delta = int(current_value) - int(baseline_value)
        if direction == "lower_is_better":
            if delta > 0:
                movement = "regression"
            elif delta < 0:
                movement = "improvement"
            else:
                movement = "unchanged"
        elif direction == "higher_is_better":
            if delta < 0:
                movement = "regression"
            elif delta > 0:
                movement = "improvement"
            else:
                movement = "unchanged"
        else:
            if delta > 0:
                movement = "increase"
            elif delta < 0:
                movement = "decrease"
            else:
                movement = "unchanged"

        entries.append(
            {
                "metric": metric,
                "dimension": dimension,
                "scope": scope,
                "direction": direction,
                "baseline": int(baseline_value),
                "current": int(current_value),
                "delta": int(delta),
                "movement": movement,
            }
        )

    return entries


def _dimension_summary(entries: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    dimensions = ("stage", "risk_trend", "overall")
    movement_keys = (
        "regression",
        "improvement",
        "unchanged",
        "increase",
        "decrease",
        "new_metric",
        "dropped_metric",
    )
    summary: dict[str, dict[str, int]] = {}
    for dimension in dimensions:
        bucket_entries = [item for item in entries if item["dimension"] == dimension]
        counts = {key: 0 for key in movement_keys}
        for item in bucket_entries:
            movement = item["movement"]
            if movement in counts:
                counts[movement] += 1
        summary[dimension] = {
            "total_metrics": len(bucket_entries),
            **counts,
        }
    return summary


def _parse_tolerance_value(metric: str, value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Tolerance value must be integer >= 0: {metric}")
    if isinstance(value, (int, float)):
        coerced = int(value)
        if coerced < 0:
            raise ValueError(f"Tolerance value must be >= 0: {metric}")
        return coerced
    raise ValueError(f"Tolerance value must be numeric: {metric}")


def _load_tolerance_map(raw: Any, *, section: str) -> dict[str, int]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"Tolerance section must be object: {section}")
    parsed: dict[str, int] = {}
    for metric, value in raw.items():
        if not isinstance(metric, str):
            continue
        parsed[metric] = _parse_tolerance_value(metric, value)
    return parsed


def _resolve_tolerances(path: Path | None) -> tuple[dict[str, int], dict[str, int], str | None]:
    if path is None:
        return (
            dict(sorted(LOWER_IS_BETTER_DEFAULTS.items())),
            dict(sorted(HIGHER_IS_BETTER_DEFAULTS.items())),
            None,
        )

    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Tolerance config not found: {path}")

    payload = _load_json_file(path)
    lower = _load_tolerance_map(payload.get("lower_is_better"), section="lower_is_better")
    higher = _load_tolerance_map(payload.get("higher_is_better"), section="higher_is_better")

    if not lower and not higher:
        lower = dict(LOWER_IS_BETTER_DEFAULTS)
        higher = dict(HIGHER_IS_BETTER_DEFAULTS)

    overlap = sorted(set(lower) & set(higher))
    if overlap:
        raise ValueError(
            "Tolerance metric cannot exist in both lower_is_better and higher_is_better: "
            + ", ".join(overlap)
        )

    return (dict(sorted(lower.items())), dict(sorted(higher.items())), str(path.resolve()))


def _evaluate_tolerances(
    *,
    baseline_metrics: dict[str, int],
    current_metrics: dict[str, int],
    lower_is_better: dict[str, int],
    higher_is_better: dict[str, int],
) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []

    for metric, tolerance in lower_is_better.items():
        baseline_value = baseline_metrics.get(metric)
        current_value = current_metrics.get(metric)
        if baseline_value is None or current_value is None:
            violations.append(
                {
                    "metric": metric,
                    "direction": "lower_is_better",
                    "tolerance": tolerance,
                    "reason": "metric_missing",
                    "baseline": baseline_value,
                    "current": current_value,
                }
            )
            continue
        adverse_delta = int(current_value) - int(baseline_value)
        if adverse_delta > int(tolerance):
            violations.append(
                {
                    "metric": metric,
                    "direction": "lower_is_better",
                    "baseline": int(baseline_value),
                    "current": int(current_value),
                    "adverse_delta": int(adverse_delta),
                    "tolerance": int(tolerance),
                    "reason": "regression_above_tolerance",
                }
            )

    for metric, tolerance in higher_is_better.items():
        baseline_value = baseline_metrics.get(metric)
        current_value = current_metrics.get(metric)
        if baseline_value is None or current_value is None:
            violations.append(
                {
                    "metric": metric,
                    "direction": "higher_is_better",
                    "tolerance": tolerance,
                    "reason": "metric_missing",
                    "baseline": baseline_value,
                    "current": current_value,
                }
            )
            continue
        adverse_delta = int(baseline_value) - int(current_value)
        if adverse_delta > int(tolerance):
            violations.append(
                {
                    "metric": metric,
                    "direction": "higher_is_better",
                    "baseline": int(baseline_value),
                    "current": int(current_value),
                    "adverse_delta": int(adverse_delta),
                    "tolerance": int(tolerance),
                    "reason": "regression_above_tolerance",
                }
            )

    return {
        "checked_metric_count": len(lower_is_better) + len(higher_is_better),
        "violation_count": len(violations),
        "passed": len(violations) == 0,
        "violations": violations,
    }


def _format_delta(value: int | None) -> str:
    if value is None:
        return "n/a"
    if value > 0:
        return f"+{value}"
    return str(value)


def _append_movement_table(
    lines: list[str],
    *,
    entries: list[dict[str, Any]],
    movement: str,
    title: str,
) -> None:
    lines.extend(["", title, ""])
    selected = [item for item in entries if item.get("movement") == movement]
    if not selected:
        lines.append("- None")
        return

    lines.extend(
        [
            "| Metric | Baseline | Current | Delta | Scope |",
            "|---|---:|---:|---:|---|",
        ]
    )
    selected.sort(
        key=lambda item: (
            -(abs(_safe_int(item.get("delta", 0)))),
            str(item.get("metric", "")),
        )
    )
    for item in selected:
        lines.append(
            f"| `{item['metric']}` | {item['baseline']} | {item['current']} | "
            f"{_format_delta(item.get('delta'))} | `{item['scope']}` |"
        )


def _render_diff_markdown(diff_payload: dict[str, Any]) -> str:
    baseline = diff_payload.get("baseline", {})
    current = diff_payload.get("current", {})
    dimension_summary = diff_payload.get("dimension_summary", {})
    entries = diff_payload.get("entries", [])
    tolerance = diff_payload.get("tolerance_evaluation", {})

    lines = [
        "# Real-Sample Baseline Diff Report",
        "",
        f"- Generated at (UTC): `{diff_payload.get('generated_at_utc', 'unknown')}`",
        f"- Baseline artifact: `{baseline.get('artifact', 'unknown')}`",
        f"- Baseline round: `{baseline.get('round_id') or 'unknown'}`",
        f"- Current artifact: `{current.get('artifact', 'unknown')}`",
        f"- Current round: `{current.get('round_id') or 'unknown'}`",
        f"- Baseline sample hash: `{baseline.get('sample_set', {}).get('sample_paths_sha256', '')}`",
        f"- Current sample hash: `{current.get('sample_set', {}).get('sample_paths_sha256', '')}`",
        "",
        "## Dimension Summary",
        "",
        "| Dimension | Regressions | Improvements | Unchanged |",
        "|---|---:|---:|---:|",
    ]

    for dimension in ("stage", "risk_trend", "overall"):
        item = (
            dimension_summary.get(dimension, {})
            if isinstance(dimension_summary, dict)
            else {}
        )
        lines.append(
            f"| `{dimension}` | {item.get('regression', 0)} | "
            f"{item.get('improvement', 0)} | {item.get('unchanged', 0)} |"
        )

    stage_entries = [item for item in entries if item.get("dimension") == "stage"]
    risk_entries = [item for item in entries if item.get("dimension") == "risk_trend"]

    lines.extend(["", "## Stage KPI Deltas"])
    _append_movement_table(
        lines,
        entries=stage_entries,
        movement="regression",
        title="### Stage Regressions",
    )
    _append_movement_table(
        lines,
        entries=stage_entries,
        movement="improvement",
        title="### Stage Improvements",
    )

    lines.extend(["", "## Risk Trend KPI Deltas"])
    _append_movement_table(
        lines,
        entries=risk_entries,
        movement="regression",
        title="### Risk Regressions",
    )
    _append_movement_table(
        lines,
        entries=risk_entries,
        movement="improvement",
        title="### Risk Improvements",
    )

    lines.extend([
        "",
        "## Tolerance Gate",
        "",
        f"- Strict mode: `{tolerance.get('strict_mode', False)}`",
        f"- Checked metrics: `{tolerance.get('checked_metric_count', 0)}`",
        f"- Violations: `{tolerance.get('violation_count', 0)}`",
        f"- Gate passed: `{tolerance.get('passed', False)}`",
    ])

    violations = tolerance.get("violations", [])
    if isinstance(violations, list) and violations:
        lines.extend(["", "### Violations", ""])
        for violation in violations:
            lines.append(
                "- "
                f"`{violation.get('metric')}` "
                f"baseline=`{violation.get('baseline')}` "
                f"current=`{violation.get('current')}` "
                f"adverse_delta=`{violation.get('adverse_delta', 'n/a')}` "
                f"tolerance=`{violation.get('tolerance')}`"
            )

    return "\n".join(lines) + "\n"


def _default_snapshot_paths(summary_json: Path, *, round_id: str) -> tuple[Path, Path]:
    baseline_root = summary_json.parent / "baselines"
    round_dir = baseline_root / round_id
    return (round_dir / "baseline-summary.json", round_dir / "baseline-summary.md")


def _run_snapshot(args: argparse.Namespace) -> int:
    summary_json = Path(args.summary_json).resolve()
    if not summary_json.exists() or not summary_json.is_file():
        print(f"Regression summary JSON not found: {summary_json}", file=sys.stderr)
        return 2

    try:
        round_id = _normalize_round_id(str(args.round))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    summary_payload = _load_json_file(summary_json)
    snapshot_payload = _build_snapshot_payload(
        round_id=round_id,
        summary_json=summary_json,
        summary_payload=summary_payload,
    )

    if args.snapshot_json_out:
        snapshot_json = Path(args.snapshot_json_out).resolve()
    else:
        snapshot_json, _ = _default_snapshot_paths(summary_json, round_id=round_id)

    if args.snapshot_markdown_out:
        snapshot_markdown = Path(args.snapshot_markdown_out).resolve()
    else:
        _, snapshot_markdown = _default_snapshot_paths(summary_json, round_id=round_id)

    _write_json_file(snapshot_json, snapshot_payload, pretty=args.pretty)
    snapshot_markdown.parent.mkdir(parents=True, exist_ok=True)
    snapshot_markdown.write_text(
        _render_snapshot_markdown(snapshot_payload),
        encoding="utf-8",
    )

    print(f"Baseline snapshot JSON: {snapshot_json}")
    print(f"Baseline snapshot Markdown: {snapshot_markdown}")
    return 0


def _run_diff(args: argparse.Namespace) -> int:
    current_path = Path(args.current_summary_json).resolve()
    if not current_path.exists() or not current_path.is_file():
        print(f"Current summary JSON not found: {current_path}", file=sys.stderr)
        return 2

    if args.baseline_json:
        baseline_path = Path(args.baseline_json).resolve()
    else:
        round_id = _normalize_round_id(str(args.baseline_round))
        baseline_root = (
            Path(args.baseline_root_dir).resolve()
            if args.baseline_root_dir
            else current_path.parent / "baselines"
        )
        baseline_path = baseline_root / round_id / "baseline-summary.json"

    if not baseline_path.exists() or not baseline_path.is_file():
        print(f"Baseline snapshot JSON not found: {baseline_path}", file=sys.stderr)
        return 2

    if args.diff_json_out:
        diff_json = Path(args.diff_json_out).resolve()
    else:
        diff_json = current_path.parent / "baseline-diff.json"

    if args.diff_markdown_out:
        diff_markdown = Path(args.diff_markdown_out).resolve()
    else:
        diff_markdown = current_path.parent / "baseline-diff.md"

    try:
        lower_tolerances, higher_tolerances, tolerance_source = _resolve_tolerances(
            Path(args.tolerances_file).resolve() if args.tolerances_file else None
        )
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    baseline_payload = _load_metrics_payload(baseline_path)
    current_payload = _load_metrics_payload(current_path)

    baseline_metrics = baseline_payload["metrics"]
    current_metrics = current_payload["metrics"]
    entries = _build_diff_entries(
        baseline_metrics=baseline_metrics,
        current_metrics=current_metrics,
    )
    dimension_summary = _dimension_summary(entries)

    tolerance_evaluation = _evaluate_tolerances(
        baseline_metrics=baseline_metrics,
        current_metrics=current_metrics,
        lower_is_better=lower_tolerances,
        higher_is_better=higher_tolerances,
    )
    tolerance_evaluation["strict_mode"] = bool(args.strict)
    tolerance_evaluation["tolerances_file"] = tolerance_source

    regression_count = sum(1 for item in entries if item.get("movement") == "regression")
    passed = tolerance_evaluation["passed"]
    exit_code = 2 if args.strict and not passed else 0

    diff_payload = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "baseline": {
            "artifact": str(baseline_path),
            "kind": baseline_payload["kind"],
            "round_id": baseline_payload.get("round_id"),
            "source_summary_json": baseline_payload.get("source_summary_json"),
            "sample_set": baseline_payload.get("sample_set", {}),
        },
        "current": {
            "artifact": str(current_path),
            "kind": current_payload["kind"],
            "round_id": args.current_round,
            "source_summary_json": current_payload.get("source_summary_json"),
            "sample_set": current_payload.get("sample_set", {}),
        },
        "dimension_summary": dimension_summary,
        "entry_counts": {
            "total_metrics": len(entries),
            "regressions": regression_count,
            "improvements": sum(
                1 for item in entries if item.get("movement") == "improvement"
            ),
        },
        "entries": entries,
        "tolerance_evaluation": tolerance_evaluation,
        "overall_status": "success" if passed else "failure",
        "overall_exit_code": exit_code,
    }

    _write_json_file(diff_json, diff_payload, pretty=args.pretty)
    diff_markdown.parent.mkdir(parents=True, exist_ok=True)
    diff_markdown.write_text(_render_diff_markdown(diff_payload), encoding="utf-8")

    print(f"Baseline diff JSON: {diff_json}")
    print(f"Baseline diff Markdown: {diff_markdown}")
    print(f"Tolerance gate passed: {tolerance_evaluation['passed']}")

    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="real_sample_baseline",
        description=(
            "Persist baseline snapshots from real-sample regression summaries and "
            "compute deterministic KPI deltas."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot_parser = subparsers.add_parser(
        "snapshot",
        help="Persist round baseline snapshot artifacts from regression-summary.json",
    )
    snapshot_parser.add_argument(
        "--summary-json",
        required=True,
        help="Path to run_real_sample_e2e_regression output summary JSON",
    )
    snapshot_parser.add_argument(
        "--round",
        required=True,
        help="Round id used for baseline snapshot namespace (for example: R10)",
    )
    snapshot_parser.add_argument(
        "--snapshot-json-out",
        help=(
            "Optional explicit baseline snapshot JSON output path "
            "(default: <summary-dir>/baselines/<round>/baseline-summary.json)"
        ),
    )
    snapshot_parser.add_argument(
        "--snapshot-markdown-out",
        help=(
            "Optional explicit baseline snapshot Markdown output path "
            "(default: <summary-dir>/baselines/<round>/baseline-summary.md)"
        ),
    )
    snapshot_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON outputs",
    )

    diff_parser = subparsers.add_parser(
        "diff",
        help="Compare current real-sample summary against a baseline snapshot",
    )
    diff_parser.add_argument(
        "--current-summary-json",
        required=True,
        help="Path to current run regression summary JSON",
    )
    baseline_group = diff_parser.add_mutually_exclusive_group(required=True)
    baseline_group.add_argument(
        "--baseline-json",
        help="Path to baseline snapshot JSON (or baseline regression summary JSON)",
    )
    baseline_group.add_argument(
        "--baseline-round",
        help="Baseline round id; resolved from --baseline-root-dir/<round>/baseline-summary.json",
    )
    diff_parser.add_argument(
        "--baseline-root-dir",
        help=(
            "Baseline root directory used with --baseline-round "
            "(default: <current-summary-dir>/baselines)"
        ),
    )
    diff_parser.add_argument(
        "--current-round",
        help="Optional label for current round (for reporting only)",
    )
    diff_parser.add_argument(
        "--diff-json-out",
        help="Optional explicit baseline diff JSON output path",
    )
    diff_parser.add_argument(
        "--diff-markdown-out",
        help="Optional explicit baseline diff Markdown output path",
    )
    diff_parser.add_argument(
        "--tolerances-file",
        default=str(DEFAULT_TOLERANCES_PATH),
        help=(
            "Tolerance config JSON path "
            f"(default: {DEFAULT_TOLERANCES_PATH})"
        ),
    )
    diff_parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail with exit code 2 when tolerance gate violations exist",
    )
    diff_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON outputs",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "snapshot":
        return _run_snapshot(args)
    if args.command == "diff":
        return _run_diff(args)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
