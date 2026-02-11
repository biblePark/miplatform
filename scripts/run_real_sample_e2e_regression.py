#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime
import json
from pathlib import Path
import shlex
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from migrator.cli import main as migrator_main

STAGES = ("parse", "map_api", "gen_ui", "sync_preview")
EXTRACTION_RISK_GATES = {
    "dataset_extraction_coverage",
    "binding_extraction_coverage",
    "event_extraction_coverage",
    "transaction_extraction_coverage",
    "script_extraction_coverage",
}
FIDELITY_RISK_GATES = {
    "unknown_tag_count",
    "unknown_attr_count",
    "roundtrip_structural_diff",
    "canonical_roundtrip_hash_match",
}
XML_PARSE_FAILURE_PREFIX = "XML parse failure:"


def _load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_file(path: Path, payload: object, *, pretty: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2 if pretty else None, ensure_ascii=False),
        encoding="utf-8",
    )


def _to_report_file_stem(xml_path: Path) -> str:
    raw = xml_path.stem.strip()
    if not raw:
        return "screen"
    stem = "".join(ch if (ch.isalnum() or ch in {"-", "_"}) else "-" for ch in raw)
    stem = stem.strip("-_")
    return stem or "screen"


def _sorted_counter(counter: Counter[str]) -> dict[str, int]:
    return {
        key: counter[key]
        for key in sorted(counter, key=lambda item: (-counter[item], item))
    }


def _collect_samples_from_dir(*, samples_dir: Path, recursive: bool) -> list[Path]:
    if not samples_dir.exists() or not samples_dir.is_dir():
        raise FileNotFoundError(f"Sample directory not found: {samples_dir}")
    pattern = "**/*.xml" if recursive else "*.xml"
    return sorted(path.resolve() for path in samples_dir.glob(pattern) if path.is_file())


def _collect_samples_from_list(*, sample_list_file: Path) -> list[Path]:
    if not sample_list_file.exists() or not sample_list_file.is_file():
        raise FileNotFoundError(f"Sample list file not found: {sample_list_file}")

    samples: list[Path] = []
    for raw_line in sample_list_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        candidate = Path(line)
        if not candidate.is_absolute():
            candidate = (sample_list_file.parent / candidate).resolve()
        else:
            candidate = candidate.resolve()
        if not candidate.exists() or not candidate.is_file():
            raise FileNotFoundError(f"Sample XML not found: {candidate}")
        if candidate.suffix.lower() != ".xml":
            raise ValueError(f"Sample entry must point to .xml file: {candidate}")
        samples.append(candidate)

    deduped: list[Path] = []
    seen: set[Path] = set()
    for sample in samples:
        if sample in seen:
            continue
        deduped.append(sample)
        seen.add(sample)
    return deduped


def _collect_samples(args: argparse.Namespace) -> list[Path]:
    if args.samples_dir:
        samples = _collect_samples_from_dir(
            samples_dir=Path(args.samples_dir).resolve(),
            recursive=args.recursive,
        )
    else:
        samples = _collect_samples_from_list(
            sample_list_file=Path(args.sample_list_file).resolve()
        )
    if not samples:
        raise FileNotFoundError("No XML samples found from the provided sample set.")
    return samples


def _extract_failed_gates(
    parse_report: dict[str, Any],
    gate_names: set[str],
) -> list[str]:
    failed: list[str] = []
    for gate in parse_report.get("gates", []):
        if not isinstance(gate, dict):
            continue
        gate_name = gate.get("name")
        if not isinstance(gate_name, str) or gate_name not in gate_names:
            continue
        if bool(gate.get("passed", False)):
            continue
        failed.append(gate_name)
    return sorted(set(failed))


def _format_status_counts(counter: Counter[str]) -> dict[str, int]:
    keys = ["success", "failure", "skipped", "pending", "missing"]
    payload: dict[str, int] = {}
    for key in keys:
        if counter.get(key, 0) > 0:
            payload[key] = counter[key]
    for key in sorted(counter):
        if key in payload:
            continue
        payload[key] = counter[key]
    return payload


def _build_migrate_e2e_args(
    *,
    xml_path: Path,
    reports_dir: Path,
    summary_out: Path,
    api_out_dir: Path,
    ui_out_dir: Path,
    preview_host_dir: Path,
    args: argparse.Namespace,
) -> list[str]:
    command = [
        "migrate-e2e",
        str(xml_path),
        "--out-dir",
        str(reports_dir),
        "--summary-out",
        str(summary_out),
        "--api-out-dir",
        str(api_out_dir),
        "--ui-out-dir",
        str(ui_out_dir),
        "--preview-host-dir",
        str(preview_host_dir),
    ]
    if args.strict:
        command.append("--strict")
    if args.capture_text:
        command.append("--capture-text")
    if args.known_tags_file:
        command.extend(["--known-tags-file", str(Path(args.known_tags_file).resolve())])
    if args.known_attrs_file:
        command.extend(["--known-attrs-file", str(Path(args.known_attrs_file).resolve())])
    if args.disable_roundtrip_gate:
        command.append("--disable-roundtrip-gate")
    if args.roundtrip_mismatch_limit is not None:
        command.extend(["--roundtrip-mismatch-limit", str(args.roundtrip_mismatch_limit)])
    if args.pretty:
        command.append("--pretty")
    return command


def _render_markdown_summary(summary: dict[str, Any]) -> str:
    lines = [
        "# Real-Sample migrate-e2e Regression Summary",
        "",
        f"- Generated at (UTC): `{summary['generated_at_utc']}`",
        f"- Out dir: `{summary['artifacts']['out_dir']}`",
        f"- Total samples: `{summary['totals']['total_samples']}`",
        f"- Success: `{summary['totals']['success_count']}`",
        f"- Failure: `{summary['totals']['failure_count']}`",
        "",
        "## Stage Status Counts",
        "",
        "| Stage | Success | Failure | Skipped | Missing |",
        "|---|---:|---:|---:|---:|",
    ]

    for stage in STAGES:
        counts = summary["stage_status_counts"].get(stage, {})
        lines.append(
            f"| `{stage}` | {counts.get('success', 0)} | {counts.get('failure', 0)} | "
            f"{counts.get('skipped', 0)} | {counts.get('missing', 0)} |"
        )

    lines.extend(["", "## Top Warnings", ""])
    top_warnings = summary.get("top_warnings", [])
    if not top_warnings:
        lines.append("- None")
    else:
        for item in top_warnings:
            lines.append(f"- `{item['count']}` x `{item['message']}`")

    lines.extend(["", "## Risk Trends", ""])
    extraction = summary["risk_trends"]["extraction"]
    lines.append(
        f"- Extraction risk files: `{extraction['files_with_risk']}` "
        f"(gate failures: `{sum(extraction['gate_failure_counts'].values())}`)"
    )
    mapping = summary["risk_trends"]["mapping"]
    lines.append(
        f"- Mapping risk files: `{mapping['files_with_risk']}` "
        f"(mapped failures: `{mapping['mapped_failure_total']}`, "
        f"unsupported: `{mapping['unsupported_total']}`)"
    )
    fidelity = summary["risk_trends"]["fidelity"]
    lines.append(
        f"- Fidelity risk files: `{fidelity['files_with_risk']}` "
        f"(gate failures: `{sum(fidelity['gate_failure_counts'].values())}`, "
        f"UI fallback warnings: `{fidelity['ui_fallback_warning_total']}`)"
    )

    lines.extend(["", "## Unresolved Malformed/XML Blockers", ""])
    blockers = summary.get("malformed_xml_blockers", [])
    if not blockers:
        lines.append("- None")
    else:
        for blocker in blockers:
            lines.append(f"- `{blocker['xml_path']}`: `{blocker['error']}`")

    lines.extend(
        [
            "",
            "## Sample Outcomes",
            "",
            "| XML | Overall | Exit | Parse | Map API | Gen UI | Sync Preview |",
            "|---|---|---:|---|---|---|---|",
        ]
    )
    for item in summary.get("samples", []):
        statuses = item.get("stage_statuses", {})
        lines.append(
            f"| `{item['xml_path']}` | `{item['overall_status']}` | `{item['exit_code']}` | "
            f"`{statuses.get('parse', 'missing')}` | `{statuses.get('map_api', 'missing')}` | "
            f"`{statuses.get('gen_ui', 'missing')}` | `{statuses.get('sync_preview', 'missing')}` |"
        )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_real_sample_e2e_regression",
        description="Run migrate-e2e across a real XML sample set and build consolidated risk summary.",
    )
    sample_input_group = parser.add_mutually_exclusive_group(required=True)
    sample_input_group.add_argument(
        "--samples-dir",
        help="Directory containing real XML samples (*.xml)",
    )
    sample_input_group.add_argument(
        "--sample-list-file",
        help="Path to newline-delimited XML sample list file",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively scan --samples-dir for XML files",
    )
    parser.add_argument(
        "--out-dir",
        default="out/real-sample-e2e-regression",
        help=(
            "Output directory for per-sample migrate-e2e artifacts and consolidated "
            "regression reports (default: out/real-sample-e2e-regression)"
        ),
    )
    parser.add_argument("--strict", action="store_true", help="Enable strict parse gates")
    parser.add_argument("--capture-text", action="store_true", help="Capture node text bodies")
    parser.add_argument("--known-tags-file", help="Known tag profile (newline-delimited text)")
    parser.add_argument("--known-attrs-file", help='Known attrs profile JSON map {"Tag":["attr"]}')
    parser.add_argument(
        "--disable-roundtrip-gate",
        action="store_true",
        help="Disable roundtrip structural/canonical gates",
    )
    parser.add_argument(
        "--roundtrip-mismatch-limit",
        type=int,
        default=200,
        help="Maximum mismatch details stored in parse report (default: 200)",
    )
    parser.add_argument(
        "--top-warning-limit",
        type=int,
        default=10,
        help="Maximum warning messages to include in top warnings (default: 10)",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON outputs")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    samples = _collect_samples(args)
    out_dir = Path(args.out_dir).resolve()
    runs_dir = out_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    stage_status_counts: dict[str, Counter[str]] = {stage: Counter() for stage in STAGES}
    stage_failure_details: dict[str, list[dict[str, Any]]] = {stage: [] for stage in STAGES}
    warning_counter: Counter[str] = Counter()

    extraction_gate_failures: Counter[str] = Counter()
    extraction_issues_by_file: dict[str, set[str]] = defaultdict(set)
    mapping_risk_files: list[dict[str, Any]] = []
    mapping_mapped_failure_total = 0
    mapping_unsupported_total = 0
    fidelity_gate_failures: Counter[str] = Counter()
    fidelity_issues_by_file: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"failed_gates": set(), "ui_fallback_warning_count": 0}
    )
    malformed_xml_blockers: list[dict[str, str]] = []

    sample_results: list[dict[str, Any]] = []
    success_count = 0
    failure_count = 0

    for index, xml_path in enumerate(samples, start=1):
        stem = _to_report_file_stem(xml_path)
        run_dir = runs_dir / f"{index:03d}-{stem}"
        reports_dir = run_dir / "reports"
        summary_out = reports_dir / f"{stem}.migration-summary.json"
        api_out_dir = run_dir / "generated" / "api"
        ui_out_dir = run_dir / "generated" / "frontend"
        preview_host_dir = run_dir / "preview-host"
        preview_host_dir.mkdir(parents=True, exist_ok=True)

        command = _build_migrate_e2e_args(
            xml_path=xml_path,
            reports_dir=reports_dir,
            summary_out=summary_out,
            api_out_dir=api_out_dir,
            ui_out_dir=ui_out_dir,
            preview_host_dir=preview_host_dir,
            args=args,
        )
        exit_code = migrator_main(command)

        if exit_code == 0:
            success_count += 1
        else:
            failure_count += 1

        summary_payload: dict[str, Any] = {}
        if summary_out.exists():
            summary_payload = _load_json_file(summary_out)

        stages = summary_payload.get("stages", {})
        stage_statuses: dict[str, str] = {}
        for stage in STAGES:
            stage_payload = stages.get(stage, {})
            status = (
                str(stage_payload.get("status"))
                if isinstance(stage_payload, dict) and stage_payload.get("status")
                else "missing"
            )
            stage_statuses[stage] = status
            stage_status_counts[stage][status] += 1
            if status == "failure":
                detail: dict[str, Any] = {
                    "xml_path": str(xml_path),
                    "summary_file": str(summary_out),
                }
                if isinstance(stage_payload, dict):
                    error = stage_payload.get("error")
                    if isinstance(error, str) and error:
                        detail["error"] = error
                stage_failure_details[stage].append(detail)

        warnings = summary_payload.get("warnings", [])
        if isinstance(warnings, list):
            for warning in warnings:
                if isinstance(warning, str) and warning:
                    warning_counter[warning] += 1

        parse_stage = stages.get("parse", {})
        if isinstance(parse_stage, dict):
            parse_error = parse_stage.get("error")
            if isinstance(parse_error, str) and parse_error.startswith(XML_PARSE_FAILURE_PREFIX):
                malformed_xml_blockers.append(
                    {
                        "xml_path": str(xml_path),
                        "error": parse_error,
                        "summary_file": str(summary_out),
                    }
                )

        reports = summary_payload.get("reports", {})
        parse_report_path = (
            Path(reports["parse_report"]).resolve()
            if isinstance(reports, dict) and isinstance(reports.get("parse_report"), str)
            else None
        )
        map_report_path = (
            Path(reports["map_api_report"]).resolve()
            if isinstance(reports, dict) and isinstance(reports.get("map_api_report"), str)
            else None
        )
        ui_report_path = (
            Path(reports["gen_ui_report"]).resolve()
            if isinstance(reports, dict) and isinstance(reports.get("gen_ui_report"), str)
            else None
        )

        if parse_report_path and parse_report_path.exists():
            parse_report = _load_json_file(parse_report_path)
            failed_extraction_gates = _extract_failed_gates(
                parse_report,
                gate_names=EXTRACTION_RISK_GATES,
            )
            for gate_name in failed_extraction_gates:
                extraction_gate_failures[gate_name] += 1
                extraction_issues_by_file[str(xml_path)].add(gate_name)

            failed_fidelity_gates = _extract_failed_gates(
                parse_report,
                gate_names=FIDELITY_RISK_GATES,
            )
            for gate_name in failed_fidelity_gates:
                fidelity_gate_failures[gate_name] += 1
                fidelity_issues_by_file[str(xml_path)]["failed_gates"].add(gate_name)

        if map_report_path and map_report_path.exists():
            map_report = _load_json_file(map_report_path)
            summary = map_report.get("summary", {})
            mapped_failure = (
                int(summary.get("mapped_failure", 0))
                if isinstance(summary, dict)
                else 0
            )
            unsupported = (
                int(summary.get("unsupported", 0))
                if isinstance(summary, dict)
                else 0
            )
            mapping_mapped_failure_total += mapped_failure
            mapping_unsupported_total += unsupported
            if mapped_failure > 0 or unsupported > 0:
                mapping_risk_files.append(
                    {
                        "xml_path": str(xml_path),
                        "mapped_failure": mapped_failure,
                        "unsupported": unsupported,
                        "report_file": str(map_report_path),
                    }
                )

        if ui_report_path and ui_report_path.exists():
            ui_report = _load_json_file(ui_report_path)
            ui_warnings = ui_report.get("warnings", [])
            if isinstance(ui_warnings, list):
                fallback_count = sum(
                    1
                    for warning in ui_warnings
                    if isinstance(warning, str) and "rendered as fallback widget." in warning
                )
                if fallback_count > 0:
                    fidelity_issues_by_file[str(xml_path)]["ui_fallback_warning_count"] += (
                        fallback_count
                    )

        sample_results.append(
            {
                "xml_path": str(xml_path),
                "run_dir": str(run_dir),
                "summary_file": str(summary_out),
                "command": shlex.join(command),
                "exit_code": exit_code,
                "overall_status": summary_payload.get("overall_status", "failure"),
                "stage_statuses": stage_statuses,
                "warning_count": len(summary_payload.get("warnings", []))
                if isinstance(summary_payload.get("warnings", []), list)
                else 0,
                "error_count": len(summary_payload.get("errors", []))
                if isinstance(summary_payload.get("errors", []), list)
                else 0,
            }
        )

    top_warning_limit = max(0, int(args.top_warning_limit))
    top_warnings = [
        {"message": warning, "count": warning_counter[warning]}
        for warning in sorted(
            warning_counter,
            key=lambda item: (-warning_counter[item], item),
        )[:top_warning_limit]
    ]

    extraction_top_files = [
        {"xml_path": file_path, "failed_gates": sorted(gates)}
        for file_path, gates in sorted(
            extraction_issues_by_file.items(),
            key=lambda item: (-len(item[1]), item[0]),
        )
    ]

    mapping_risk_files.sort(
        key=lambda item: (
            -(int(item["mapped_failure"]) + int(item["unsupported"])),
            item["xml_path"],
        )
    )

    fidelity_top_files = [
        {
            "xml_path": file_path,
            "failed_gates": sorted(issue["failed_gates"]),
            "ui_fallback_warning_count": int(issue["ui_fallback_warning_count"]),
        }
        for file_path, issue in sorted(
            fidelity_issues_by_file.items(),
            key=lambda item: (
                -(len(item[1]["failed_gates"]) + int(item[1]["ui_fallback_warning_count"])),
                item[0],
            ),
        )
        if issue["failed_gates"] or int(issue["ui_fallback_warning_count"]) > 0
    ]

    summary_payload = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "command": "run_real_sample_e2e_regression",
        "inputs": {
            "samples_dir": str(Path(args.samples_dir).resolve()) if args.samples_dir else None,
            "sample_list_file": (
                str(Path(args.sample_list_file).resolve()) if args.sample_list_file else None
            ),
            "recursive": bool(args.recursive),
            "strict": bool(args.strict),
            "capture_text": bool(args.capture_text),
            "known_tags_file": (
                str(Path(args.known_tags_file).resolve()) if args.known_tags_file else None
            ),
            "known_attrs_file": (
                str(Path(args.known_attrs_file).resolve()) if args.known_attrs_file else None
            ),
            "disable_roundtrip_gate": bool(args.disable_roundtrip_gate),
            "roundtrip_mismatch_limit": int(args.roundtrip_mismatch_limit),
        },
        "artifacts": {
            "out_dir": str(out_dir),
            "runs_dir": str(runs_dir),
            "summary_json": str((out_dir / "regression-summary.json").resolve()),
            "summary_markdown": str((out_dir / "regression-summary.md").resolve()),
        },
        "totals": {
            "total_samples": len(samples),
            "success_count": success_count,
            "failure_count": failure_count,
        },
        "stage_status_counts": {
            stage: _format_status_counts(counter)
            for stage, counter in stage_status_counts.items()
        },
        "stage_failure_details": stage_failure_details,
        "top_warnings": top_warnings,
        "risk_trends": {
            "extraction": {
                "files_with_risk": len(extraction_issues_by_file),
                "gate_failure_counts": _sorted_counter(extraction_gate_failures),
                "top_files": extraction_top_files,
            },
            "mapping": {
                "files_with_risk": len(mapping_risk_files),
                "mapped_failure_total": mapping_mapped_failure_total,
                "unsupported_total": mapping_unsupported_total,
                "top_files": mapping_risk_files,
            },
            "fidelity": {
                "files_with_risk": len(fidelity_top_files),
                "gate_failure_counts": _sorted_counter(fidelity_gate_failures),
                "ui_fallback_warning_total": sum(
                    int(item["ui_fallback_warning_count"]) for item in fidelity_top_files
                ),
                "top_files": fidelity_top_files,
            },
        },
        "malformed_xml_blockers": malformed_xml_blockers,
        "samples": sample_results,
        "overall_status": "success" if failure_count == 0 else "failure",
        "overall_exit_code": 0 if failure_count == 0 else 2,
    }

    summary_json = out_dir / "regression-summary.json"
    summary_md = out_dir / "regression-summary.md"
    _write_json_file(summary_json, summary_payload, pretty=args.pretty)
    summary_md.write_text(_render_markdown_summary(summary_payload), encoding="utf-8")

    print(f"Regression summary JSON: {summary_json}")
    print(f"Regression summary Markdown: {summary_md}")
    return int(summary_payload["overall_exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
