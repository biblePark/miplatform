#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

STAGE_ORDER = (
    "parse",
    "map_api",
    "gen_ui",
    "fidelity_audit",
    "sync_preview",
    "preview_smoke",
)
SUPPORTED_REPORT_TYPES = (
    "migration_summary",
    "regression_summary",
    "prototype_acceptance",
)


def _to_int(value: Any, *, default: int = 0) -> int:
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


def _to_float(value: Any, *, default: float = 0.0) -> float:
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


def _to_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text if text else None
    return str(value)


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object payload: {path}")
    return payload


def _collect_report_files(raw_inputs: list[str]) -> tuple[list[Path], set[Path]]:
    collected: list[Path] = []
    explicit_files: set[Path] = set()

    for raw in raw_inputs:
        candidate = Path(raw).resolve()
        if candidate.is_file():
            resolved = candidate.resolve()
            collected.append(resolved)
            explicit_files.add(resolved)
            continue
        if candidate.is_dir():
            for report_file in sorted(path for path in candidate.rglob("*.json") if path.is_file()):
                collected.append(report_file.resolve())
            continue
        raise FileNotFoundError(f"Input path not found: {candidate}")

    deduped = sorted(set(collected), key=lambda item: str(item))
    if not deduped:
        raise FileNotFoundError("No JSON files found from the provided inputs.")
    return deduped, explicit_files


def _detect_report_type(payload: dict[str, Any]) -> str | None:
    if isinstance(payload.get("verdict"), str) and isinstance(payload.get("kpi_results"), list):
        return "prototype_acceptance"
    if isinstance(payload.get("risk_trends"), dict) and isinstance(
        payload.get("stage_status_counts"),
        dict,
    ):
        return "regression_summary"
    if isinstance(payload.get("stages"), dict):
        return "migration_summary"
    return None


def _ordered_stage_statuses(stages: dict[str, Any]) -> dict[str, str]:
    ordered: dict[str, str] = {}

    for stage_name in STAGE_ORDER:
        stage_payload = stages.get(stage_name)
        if not isinstance(stage_payload, dict):
            continue
        status = _to_optional_str(stage_payload.get("status"))
        if status is None:
            continue
        ordered[stage_name] = status

    for stage_name in sorted(name for name in stages.keys() if isinstance(name, str)):
        if stage_name in ordered:
            continue
        stage_payload = stages.get(stage_name)
        if not isinstance(stage_payload, dict):
            continue
        status = _to_optional_str(stage_payload.get("status"))
        if status is None:
            continue
        ordered[stage_name] = status

    return ordered


def _ordered_stage_failure_counts(stage_status_counts: dict[str, Any]) -> dict[str, int]:
    ordered: dict[str, int] = {}

    for stage_name in STAGE_ORDER:
        raw_counts = stage_status_counts.get(stage_name)
        if not isinstance(raw_counts, dict):
            continue
        ordered[stage_name] = _to_int(raw_counts.get("failure", 0))

    for stage_name in sorted(name for name in stage_status_counts.keys() if isinstance(name, str)):
        if stage_name in ordered:
            continue
        raw_counts = stage_status_counts.get(stage_name)
        if not isinstance(raw_counts, dict):
            continue
        ordered[stage_name] = _to_int(raw_counts.get("failure", 0))

    return ordered


def _parse_migration_summary(payload: dict[str, Any]) -> dict[str, Any]:
    stages = payload.get("stages", {})
    if not isinstance(stages, dict):
        raise ValueError("migration_summary report must include object field: stages")

    warnings = payload.get("warnings", [])
    errors = payload.get("errors", [])

    gen_ui = stages.get("gen_ui", {})
    fidelity = stages.get("fidelity_audit", {})
    if not isinstance(gen_ui, dict):
        gen_ui = {}
    if not isinstance(fidelity, dict):
        fidelity = {}

    missing_node_count = _to_int(fidelity.get("missing_node_count", 0))
    position_style_nodes_with_risk = _to_int(
        fidelity.get("position_style_nodes_with_risk", 0)
    )

    return {
        "screen_id": _to_optional_str(payload.get("screen_id")),
        "overall_status": _to_optional_str(payload.get("overall_status")) or "unknown",
        "overall_exit_code": _to_int(payload.get("overall_exit_code", 0)),
        "stage_statuses": _ordered_stage_statuses(stages),
        "warning_count": len(warnings) if isinstance(warnings, list) else 0,
        "error_count": len(errors) if isinstance(errors, list) else 0,
        "fidelity_risk_detected": bool(
            fidelity.get("risk_detected")
            or missing_node_count > 0
            or position_style_nodes_with_risk > 0
        ),
        "missing_node_count": missing_node_count,
        "position_style_nodes_with_risk": position_style_nodes_with_risk,
        "unsupported_event_bindings": _to_int(gen_ui.get("unsupported_event_bindings", 0)),
        "event_runtime_wiring_coverage_ratio": round(
            _to_float(gen_ui.get("event_runtime_wiring_coverage_ratio", 1.0)),
            6,
        ),
    }


def _parse_regression_summary(payload: dict[str, Any]) -> dict[str, Any]:
    totals = payload.get("totals", {})
    stage_status_counts = payload.get("stage_status_counts", {})
    risk_trends = payload.get("risk_trends", {})

    if not isinstance(totals, dict):
        raise ValueError("regression_summary report must include object field: totals")
    if not isinstance(stage_status_counts, dict):
        raise ValueError(
            "regression_summary report must include object field: stage_status_counts"
        )
    if not isinstance(risk_trends, dict):
        raise ValueError("regression_summary report must include object field: risk_trends")

    extraction = risk_trends.get("extraction", {})
    mapping = risk_trends.get("mapping", {})
    fidelity = risk_trends.get("fidelity", {})
    if not isinstance(extraction, dict):
        extraction = {}
    if not isinstance(mapping, dict):
        mapping = {}
    if not isinstance(fidelity, dict):
        fidelity = {}

    blockers = payload.get("malformed_xml_blockers", [])
    return {
        "overall_status": _to_optional_str(payload.get("overall_status")) or "unknown",
        "overall_exit_code": _to_int(payload.get("overall_exit_code", 0)),
        "total_samples": _to_int(totals.get("total_samples", 0)),
        "success_count": _to_int(totals.get("success_count", 0)),
        "failure_count": _to_int(totals.get("failure_count", 0)),
        "stage_failure_counts": _ordered_stage_failure_counts(stage_status_counts),
        "malformed_xml_blocker_count": len(blockers) if isinstance(blockers, list) else 0,
        "risk_trends": {
            "extraction": {
                "files_with_risk": _to_int(extraction.get("files_with_risk", 0)),
                "gate_failure_total": sum(
                    _to_int(value)
                    for value in (extraction.get("gate_failure_counts", {}) or {}).values()
                ),
            },
            "mapping": {
                "files_with_risk": _to_int(mapping.get("files_with_risk", 0)),
                "mapped_failure_total": _to_int(mapping.get("mapped_failure_total", 0)),
                "unsupported_total": _to_int(mapping.get("unsupported_total", 0)),
            },
            "fidelity": {
                "files_with_risk": _to_int(fidelity.get("files_with_risk", 0)),
                "gate_failure_total": sum(
                    _to_int(value)
                    for value in (fidelity.get("gate_failure_counts", {}) or {}).values()
                ),
                "missing_node_total": _to_int(fidelity.get("missing_node_total", 0)),
                "position_style_nodes_with_risk_total": _to_int(
                    fidelity.get("position_style_nodes_with_risk_total", 0)
                ),
                "ui_fallback_warning_total": _to_int(
                    fidelity.get("ui_fallback_warning_total", 0)
                ),
            },
        },
    }


def _parse_prototype_acceptance(payload: dict[str, Any]) -> dict[str, Any]:
    totals = payload.get("totals", {})
    kpi_results = payload.get("kpi_results", [])
    if not isinstance(totals, dict):
        raise ValueError("prototype_acceptance report must include object field: totals")
    if not isinstance(kpi_results, list):
        raise ValueError(
            "prototype_acceptance report must include list field: kpi_results"
        )

    failed_kpi_names = [
        item["name"]
        for item in kpi_results
        if isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and not bool(item.get("passed"))
    ]
    passed_kpi_count = sum(
        1 for item in kpi_results if isinstance(item, dict) and bool(item.get("passed"))
    )

    return {
        "verdict": _to_optional_str(payload.get("verdict")) or "unknown",
        "total_migration_summaries": _to_int(totals.get("total_migration_summaries", 0)),
        "failed_migration_count": _to_int(totals.get("failed_migration_count", 0)),
        "fidelity_risk_count": _to_int(totals.get("fidelity_risk_count", 0)),
        "unsupported_event_bindings": _to_int(totals.get("unsupported_event_bindings", 0)),
        "unresolved_transaction_adapter_signals": _to_int(
            totals.get("unresolved_transaction_adapter_signals", 0)
        ),
        "event_runtime_wiring_coverage_ratio": round(
            _to_float(totals.get("event_runtime_wiring_coverage_ratio", 1.0)),
            6,
        ),
        "total_kpi_count": len(kpi_results),
        "passed_kpi_count": passed_kpi_count,
        "failed_kpi_count": len(failed_kpi_names),
        "failed_kpi_names": failed_kpi_names,
    }


PARSERS: dict[str, Any] = {
    "migration_summary": _parse_migration_summary,
    "regression_summary": _parse_regression_summary,
    "prototype_acceptance": _parse_prototype_acceptance,
}


def _render_migration_summary_text(summary: dict[str, Any]) -> list[str]:
    stage_statuses = summary.get("stage_statuses", {})
    stage_line = ", ".join(
        f"{name}={status}" for name, status in stage_statuses.items()
    )
    return [
        f"- overall: {summary['overall_status']} (exit={summary['overall_exit_code']})",
        f"- screen_id: {summary.get('screen_id') or 'unknown'}",
        f"- stages: {stage_line if stage_line else 'none'}",
        f"- warnings/errors: {summary['warning_count']}/{summary['error_count']}",
        (
            "- fidelity_risk: "
            f"{summary['fidelity_risk_detected']} "
            f"(missing_nodes={summary['missing_node_count']}, "
            "position_style_nodes_with_risk="
            f"{summary['position_style_nodes_with_risk']})"
        ),
        (
            "- event_wiring: "
            f"unsupported={summary['unsupported_event_bindings']}, "
            "coverage_ratio="
            f"{summary['event_runtime_wiring_coverage_ratio']}"
        ),
    ]


def _render_regression_summary_text(summary: dict[str, Any]) -> list[str]:
    stage_failures = summary.get("stage_failure_counts", {})
    stage_line = ", ".join(
        f"{name}={count}" for name, count in stage_failures.items()
    )
    extraction = summary["risk_trends"]["extraction"]
    mapping = summary["risk_trends"]["mapping"]
    fidelity = summary["risk_trends"]["fidelity"]

    return [
        f"- overall: {summary['overall_status']} (exit={summary['overall_exit_code']})",
        (
            "- totals: "
            f"total={summary['total_samples']}, "
            f"success={summary['success_count']}, "
            f"failure={summary['failure_count']}"
        ),
        f"- stage_failures: {stage_line if stage_line else 'none'}",
        (
            "- extraction_risk: "
            f"files={extraction['files_with_risk']}, "
            f"gate_failures={extraction['gate_failure_total']}"
        ),
        (
            "- mapping_risk: "
            f"files={mapping['files_with_risk']}, "
            f"mapped_failure_total={mapping['mapped_failure_total']}, "
            f"unsupported_total={mapping['unsupported_total']}"
        ),
        (
            "- fidelity_risk: "
            f"files={fidelity['files_with_risk']}, "
            f"gate_failures={fidelity['gate_failure_total']}, "
            f"missing_nodes={fidelity['missing_node_total']}, "
            "position_style_nodes_with_risk="
            f"{fidelity['position_style_nodes_with_risk_total']}, "
            f"ui_fallback_warnings={fidelity['ui_fallback_warning_total']}"
        ),
        f"- malformed_xml_blockers: {summary['malformed_xml_blocker_count']}",
    ]


def _render_prototype_acceptance_text(summary: dict[str, Any]) -> list[str]:
    failed_kpis = summary.get("failed_kpi_names", [])
    failed_kpi_text = ", ".join(failed_kpis) if failed_kpis else "none"

    return [
        f"- verdict: {summary['verdict']}",
        f"- total_migration_summaries: {summary['total_migration_summaries']}",
        f"- failed_migration_count: {summary['failed_migration_count']}",
        f"- fidelity_risk_count: {summary['fidelity_risk_count']}",
        f"- unsupported_event_bindings: {summary['unsupported_event_bindings']}",
        (
            "- unresolved_transaction_adapter_signals: "
            f"{summary['unresolved_transaction_adapter_signals']}"
        ),
        (
            "- event_runtime_wiring_coverage_ratio: "
            f"{summary['event_runtime_wiring_coverage_ratio']}"
        ),
        (
            "- kpi_results: "
            f"passed={summary['passed_kpi_count']}/{summary['total_kpi_count']}, "
            f"failed={summary['failed_kpi_count']}"
        ),
        f"- failed_kpis: {failed_kpi_text}",
    ]


TEXT_RENDERERS: dict[str, Any] = {
    "migration_summary": _render_migration_summary_text,
    "regression_summary": _render_regression_summary_text,
    "prototype_acceptance": _render_prototype_acceptance_text,
}


def _render_text_reports(reports: list[dict[str, Any]]) -> str:
    lines: list[str] = []

    for index, report in enumerate(reports):
        if index > 0:
            lines.append("")
        lines.append(f"[{report['report_type']}] {report['source_file']}")
        renderer = TEXT_RENDERERS[report["report_type"]]
        lines.extend(renderer(report["summary"]))

    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="report_view",
        description=(
            "Parse and display migration report artifacts "
            "(migration summary, regression summary, prototype acceptance)."
        ),
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Report JSON file path(s) or directory path(s) to scan recursively.",
    )
    parser.add_argument(
        "--report-type",
        choices=("auto",) + SUPPORTED_REPORT_TYPES,
        default="auto",
        help="Force report type; use auto to detect from report payload (default: auto).",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text).",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output when --format=json.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        report_files, explicit_files = _collect_report_files(args.inputs)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    parsed_reports: list[dict[str, Any]] = []
    skipped_unknown_count = 0
    errors: list[str] = []

    for report_file in report_files:
        try:
            payload = _load_json_object(report_file)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"{report_file}: {exc}")
            continue

        report_type = args.report_type
        if report_type == "auto":
            detected = _detect_report_type(payload)
            if detected is None:
                if report_file in explicit_files:
                    errors.append(f"Unsupported report contract: {report_file}")
                else:
                    skipped_unknown_count += 1
                continue
            report_type = detected

        try:
            parser_fn = PARSERS[report_type]
            parsed_summary = parser_fn(payload)
        except (KeyError, ValueError, TypeError) as exc:
            errors.append(f"{report_file}: {exc}")
            continue

        parsed_reports.append(
            {
                "schema_version": 1,
                "source_file": str(report_file),
                "report_type": report_type,
                "generated_at_utc": _to_optional_str(payload.get("generated_at_utc")),
                "summary": parsed_summary,
            }
        )

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 2

    if not parsed_reports:
        print("No supported report files found from the provided inputs.", file=sys.stderr)
        return 2

    parsed_reports.sort(key=lambda item: (item["report_type"], item["source_file"]))
    if args.format == "json":
        output_payload = {
            "schema_version": 1,
            "report_count": len(parsed_reports),
            "reports": parsed_reports,
        }
        print(
            json.dumps(
                output_payload,
                indent=2 if args.pretty else None,
                ensure_ascii=False,
            )
        )
    else:
        print(_render_text_reports(parsed_reports), end="")

    if skipped_unknown_count > 0:
        print(
            f"Skipped unsupported JSON files: {skipped_unknown_count}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
