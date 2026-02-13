from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

from .api_mapping import generate_api_mapping_artifacts
from .behavior_store_codegen import generate_behavior_store_artifacts
from .fidelity_audit import (
    FidelityAuditStrictError,
    enforce_fidelity_audit_strict,
    generate_fidelity_audit_report,
)
from .models import ParseConfig
from .parser import ParseStrictError, parse_xml_file
from .preview_sync import sync_preview_host
from .prototype_acceptance import (
    build_prototype_acceptance_thresholds,
    generate_prototype_acceptance_report,
)
from .ui_codegen import generate_ui_codegen_artifacts

STRICT_GATE_FAILURE_PREFIX = "Strict parse failed for gates:"
XML_PARSE_FAILURE_PREFIX = "XML parse failure:"
FAILURE_LEADERBOARD_LIMIT = 10
MIGRATE_E2E_COMMAND_NAME = "migrate-e2e"
PROTOTYPE_ACCEPT_COMMAND_NAME = "prototype-accept"


def _load_known_tags(path: str | None) -> set[str] | None:
    if not path:
        return None
    file_path = Path(path).resolve()
    tags = {
        line.strip()
        for line in file_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    return tags


def _load_known_attrs(path: str | None) -> dict[str, set[str]] | None:
    if not path:
        return None
    file_path = Path(path).resolve()
    raw = json.loads(file_path.read_text(encoding="utf-8"))
    return {tag: set(attrs) for tag, attrs in raw.items()}


def _add_common_parse_options(command: argparse.ArgumentParser) -> None:
    command.add_argument("--strict", action="store_true", help="Fail when validation gates fail")
    command.add_argument("--capture-text", action="store_true", help="Capture node text bodies")
    command.add_argument(
        "--known-tags-file",
        help="Optional newline-delimited tag list used for unknown-tag gate",
    )
    command.add_argument(
        "--known-attrs-file",
        help='Optional JSON map: {"TagName": ["attr1"], "*": ["globalAttr"]}',
    )
    command.add_argument(
        "--disable-roundtrip-gate",
        action="store_true",
        help="Disable roundtrip structural/canonical gates",
    )
    command.add_argument(
        "--roundtrip-mismatch-limit",
        type=int,
        default=200,
        help="Maximum mismatch details stored in report (default: 200)",
    )


def _build_parse_config(args: argparse.Namespace) -> ParseConfig:
    return ParseConfig(
        strict=args.strict,
        known_tags=_load_known_tags(args.known_tags_file),
        known_attrs_by_tag=_load_known_attrs(args.known_attrs_file),
        capture_text=args.capture_text,
        enable_roundtrip_gate=not args.disable_roundtrip_gate,
        roundtrip_mismatch_limit=max(0, args.roundtrip_mismatch_limit),
    )


def _write_json_file(path: Path, payload: object, *, pretty: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2 if pretty else None, ensure_ascii=False),
        encoding="utf-8",
    )


def _classify_parse_failure(error_message: str) -> str:
    if error_message.startswith(STRICT_GATE_FAILURE_PREFIX):
        return "strict_gate_failure"
    if error_message.startswith(XML_PARSE_FAILURE_PREFIX):
        return "xml_parse_failure"
    return "parse_failure"


def _extract_failed_gate_names(error_message: str) -> list[str]:
    if not error_message.startswith(STRICT_GATE_FAILURE_PREFIX):
        return []
    gates_text = error_message.removeprefix(STRICT_GATE_FAILURE_PREFIX).strip()
    if not gates_text:
        return []
    return sorted({gate.strip() for gate in gates_text.split(",") if gate.strip()})


def _as_non_strict_config(config: ParseConfig) -> ParseConfig:
    return ParseConfig(
        strict=False,
        known_tags=config.known_tags,
        known_attrs_by_tag=config.known_attrs_by_tag,
        capture_text=config.capture_text,
        enable_roundtrip_gate=config.enable_roundtrip_gate,
        roundtrip_mismatch_limit=config.roundtrip_mismatch_limit,
    )


def _accumulate_gate_counts(
    gate_counts: dict[str, dict[str, int]],
    gates: list[object],
) -> None:
    for gate in gates:
        gate_name = getattr(gate, "name")
        passed = bool(getattr(gate, "passed"))
        if gate_name not in gate_counts:
            gate_counts[gate_name] = {"pass_count": 0, "fail_count": 0}
        if passed:
            gate_counts[gate_name]["pass_count"] += 1
        else:
            gate_counts[gate_name]["fail_count"] += 1


def _sorted_counter(counter: Counter[str]) -> dict[str, int]:
    return {
        key: counter[key]
        for key in sorted(counter, key=lambda item: (-counter[item], item))
    }


def _build_failure_file_leaderboard(
    *,
    failure_gates_by_file: dict[str, set[str]],
    failure_reasons_by_file: dict[str, set[str]],
    limit: int,
) -> list[dict[str, object]]:
    leaderboard: list[dict[str, object]] = []
    all_files = sorted(set(failure_reasons_by_file) | set(failure_gates_by_file))
    for file_path in all_files:
        failed_gates = sorted(failure_gates_by_file.get(file_path, set()))
        leaderboard.append(
            {
                "file": file_path,
                "failed_gate_count": len(failed_gates),
                "failed_gates": failed_gates,
                "failure_reasons": sorted(failure_reasons_by_file.get(file_path, set())),
            }
        )
    leaderboard.sort(key=lambda item: (-int(item["failed_gate_count"]), str(item["file"])))
    return leaderboard[: max(0, limit)]


def _to_report_file_stem(xml_path: Path) -> str:
    raw = xml_path.stem.strip()
    if not raw:
        return "screen"
    stem = "".join(ch if (ch.isalnum() or ch in {"-", "_"}) else "-" for ch in raw)
    stem = stem.strip("-_")
    return stem or "screen"


def _dedupe_preserve_order(paths: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if path in seen:
            continue
        deduped.append(path)
        seen.add(path)
    return deduped


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mifl-migrator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_cmd = subparsers.add_parser("parse", help="Parse one XML file into IR/report JSON")
    parse_cmd.add_argument("xml_path", help="Path to source XML file")
    parse_cmd.add_argument("--out", required=True, help="Output JSON report path")
    _add_common_parse_options(parse_cmd)
    parse_cmd.add_argument("--pretty", action="store_true", help="Pretty-print output JSON")

    batch_cmd = subparsers.add_parser(
        "batch-parse",
        help="Parse multiple XML files under a directory and produce per-file reports",
    )
    batch_cmd.add_argument("input_dir", help="Directory containing XML files")
    batch_cmd.add_argument("--out-dir", required=True, help="Directory for per-file JSON reports")
    batch_cmd.add_argument(
        "--summary-out",
        required=True,
        help="Output path for batch summary JSON",
    )
    batch_cmd.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively scan for XML files",
    )
    _add_common_parse_options(batch_cmd)
    batch_cmd.add_argument("--pretty", action="store_true", help="Pretty-print JSON outputs")

    map_api_cmd = subparsers.add_parser(
        "map-api",
        help="Map TransactionIR to Express route/service stubs and mapping report",
    )
    map_api_cmd.add_argument("xml_path", help="Path to source XML file")
    map_api_cmd.add_argument(
        "--out-dir",
        required=True,
        help="Directory where generated API route/service stubs are written",
    )
    map_api_cmd.add_argument(
        "--report-out",
        required=True,
        help="Output path for mapping report JSON",
    )
    _add_common_parse_options(map_api_cmd)
    map_api_cmd.add_argument("--pretty", action="store_true", help="Pretty-print JSON outputs")

    gen_ui_cmd = subparsers.add_parser(
        "gen-ui",
        help="Generate first-pass React TSX screen scaffold from parsed ScreenIR",
    )
    gen_ui_cmd.add_argument("xml_path", help="Path to source XML file")
    gen_ui_cmd.add_argument(
        "--out-dir",
        required=True,
        help="Directory where generated TSX screen files are written",
    )
    gen_ui_cmd.add_argument(
        "--report-out",
        required=True,
        help="Output path for UI codegen report JSON",
    )
    _add_common_parse_options(gen_ui_cmd)
    gen_ui_cmd.add_argument("--pretty", action="store_true", help="Pretty-print JSON outputs")

    fidelity_audit_cmd = subparsers.add_parser(
        "fidelity-audit",
        help="Compare XML node/style inventory against generated UI TSX trace inventory",
    )
    fidelity_audit_cmd.add_argument("xml_path", help="Path to source XML file")
    fidelity_audit_cmd.add_argument(
        "--generated-ui-file",
        required=True,
        help="Generated UI TSX screen file path to audit",
    )
    fidelity_audit_cmd.add_argument(
        "--report-out",
        required=True,
        help="Output path for fidelity audit report JSON",
    )
    _add_common_parse_options(fidelity_audit_cmd)
    fidelity_audit_cmd.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON outputs",
    )

    gen_behavior_store_cmd = subparsers.add_parser(
        "gen-behavior-store",
        help="Generate Zustand behavior store/action scaffolds from ScreenIR events/bindings/transactions",
    )
    gen_behavior_store_cmd.add_argument("xml_path", help="Path to source XML file")
    gen_behavior_store_cmd.add_argument(
        "--out-dir",
        required=True,
        help="Directory where generated behavior scaffold files are written",
    )
    gen_behavior_store_cmd.add_argument(
        "--report-out",
        required=True,
        help="Output path for behavior store codegen report JSON",
    )
    _add_common_parse_options(gen_behavior_store_cmd)
    gen_behavior_store_cmd.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON outputs",
    )

    sync_preview_cmd = subparsers.add_parser(
        "sync-preview",
        help="Sync preview-host manifest/registry with generated screen modules",
    )
    sync_preview_cmd.add_argument(
        "--generated-screens-dir",
        default="generated/frontend/src/screens",
        help="Directory containing generated screen entry modules (default: generated/frontend/src/screens)",
    )
    sync_preview_cmd.add_argument(
        "--preview-host-dir",
        default="preview-host",
        help="Preview host root directory (default: preview-host)",
    )
    sync_preview_cmd.add_argument(
        "--manifest-file",
        help="Optional explicit output path for screens manifest JSON",
    )
    sync_preview_cmd.add_argument(
        "--registry-generated-file",
        help="Optional explicit output path for generated registry TypeScript module",
    )
    sync_preview_cmd.add_argument(
        "--report-out",
        help="Optional output path for sync report JSON",
    )
    sync_preview_cmd.add_argument("--pretty", action="store_true", help="Pretty-print JSON outputs")

    migrate_e2e_cmd = subparsers.add_parser(
        MIGRATE_E2E_COMMAND_NAME,
        help="Run parse/map-api/gen-ui/fidelity-audit/sync-preview for one XML and emit consolidated summary JSON",
    )
    migrate_e2e_cmd.add_argument("xml_path", help="Path to source XML file")
    migrate_e2e_cmd.add_argument(
        "--out-dir",
        default="out/e2e",
        help="Directory for stage report files and default summary output path (default: out/e2e)",
    )
    migrate_e2e_cmd.add_argument(
        "--summary-out",
        help="Optional explicit output path for consolidated summary JSON",
    )
    migrate_e2e_cmd.add_argument(
        "--parse-report-out",
        help="Optional explicit output path for parse stage report JSON",
    )
    migrate_e2e_cmd.add_argument(
        "--map-report-out",
        help="Optional explicit output path for map-api stage report JSON",
    )
    migrate_e2e_cmd.add_argument(
        "--ui-report-out",
        help="Optional explicit output path for gen-ui stage report JSON",
    )
    migrate_e2e_cmd.add_argument(
        "--fidelity-report-out",
        help="Optional explicit output path for fidelity-audit stage report JSON",
    )
    migrate_e2e_cmd.add_argument(
        "--preview-report-out",
        help="Optional explicit output path for sync-preview stage report JSON",
    )
    migrate_e2e_cmd.add_argument(
        "--api-out-dir",
        default="generated/api",
        help="Directory where generated API route/service stubs are written (default: generated/api)",
    )
    migrate_e2e_cmd.add_argument(
        "--ui-out-dir",
        default="generated/frontend",
        help="Directory where generated UI files are written (default: generated/frontend)",
    )
    migrate_e2e_cmd.add_argument(
        "--preview-host-dir",
        default="preview-host",
        help="Preview host root directory (default: preview-host)",
    )
    migrate_e2e_cmd.add_argument(
        "--manifest-file",
        help="Optional explicit output path for screens manifest JSON",
    )
    migrate_e2e_cmd.add_argument(
        "--registry-generated-file",
        help="Optional explicit output path for generated registry TypeScript module",
    )
    _add_common_parse_options(migrate_e2e_cmd)
    migrate_e2e_cmd.add_argument("--pretty", action="store_true", help="Pretty-print JSON outputs")

    prototype_accept_cmd = subparsers.add_parser(
        PROTOTYPE_ACCEPT_COMMAND_NAME,
        help="Evaluate migrate-e2e summary artifacts against prototype KPI thresholds",
    )
    prototype_accept_cmd.add_argument(
        "summary_artifacts",
        nargs="+",
        help="Migration summary JSON file(s) or directories containing *.migration-summary.json",
    )
    prototype_accept_cmd.add_argument(
        "--report-out",
        required=True,
        help="Output path for prototype acceptance report JSON",
    )
    prototype_accept_cmd.add_argument(
        "--thresholds-file",
        help="Optional JSON file with KPI threshold overrides",
    )
    prototype_accept_cmd.add_argument(
        "--max-failed-migration-count",
        type=int,
        help="Maximum allowed count of non-success migration summaries",
    )
    prototype_accept_cmd.add_argument(
        "--max-fidelity-risk-count",
        type=int,
        help="Maximum allowed count of summaries with fidelity risks",
    )
    prototype_accept_cmd.add_argument(
        "--min-event-runtime-wiring-coverage-ratio",
        type=float,
        help="Minimum required aggregate runtime event wiring coverage ratio (0.0-1.0)",
    )
    prototype_accept_cmd.add_argument(
        "--max-unsupported-event-bindings",
        type=int,
        help="Maximum allowed aggregate unsupported event bindings",
    )
    prototype_accept_cmd.add_argument(
        "--max-unresolved-transaction-adapter-signals",
        type=int,
        help="Maximum allowed aggregate unresolved transaction adapter readiness signals",
    )
    prototype_accept_cmd.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON outputs",
    )

    return parser


def run_parse(args: argparse.Namespace) -> int:
    config = _build_parse_config(args)
    report = parse_xml_file(args.xml_path, config=config)
    out_path = Path(args.out).resolve()
    _write_json_file(out_path, report.to_dict(), pretty=args.pretty)
    return 0


def run_batch_parse(args: argparse.Namespace) -> int:
    input_dir = Path(args.input_dir).resolve()
    if not input_dir.exists() or not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    out_dir = Path(args.out_dir).resolve()
    summary_out = Path(args.summary_out).resolve()
    config = _build_parse_config(args)
    non_strict_config = _as_non_strict_config(config)

    pattern = "**/*.xml" if args.recursive else "*.xml"
    xml_files = sorted(input_dir.glob(pattern))
    xml_file_paths = [path for path in xml_files if path.is_file()]

    reports_written = 0
    failures: list[dict[str, object]] = []
    gate_counts: dict[str, dict[str, int]] = {}
    failure_reason_counts: Counter[str] = Counter()
    failure_file_counts: Counter[str] = Counter()
    failure_gates_by_file: dict[str, set[str]] = defaultdict(set)
    failure_reasons_by_file: dict[str, set[str]] = defaultdict(set)

    for xml_file in xml_file_paths:
        try:
            report = parse_xml_file(xml_file, config=config)
            relative = xml_file.relative_to(input_dir)
            report_path = out_dir / relative.with_suffix(".json")
            _write_json_file(report_path, report.to_dict(), pretty=args.pretty)
            _accumulate_gate_counts(gate_counts, report.gates)
            reports_written += 1
        except ParseStrictError as exc:
            file_path = str(xml_file)
            error_message = str(exc)
            failure_reason = _classify_parse_failure(error_message)
            failed_gates = _extract_failed_gate_names(error_message)

            if failure_reason == "strict_gate_failure":
                try:
                    report = parse_xml_file(xml_file, config=non_strict_config)
                    _accumulate_gate_counts(gate_counts, report.gates)
                    if not failed_gates:
                        failed_gates = sorted(
                            gate.name for gate in report.gates if not gate.passed
                        )
                except ParseStrictError:
                    # Defensive fallback: strict disabled should not raise for gate failures.
                    pass

            failure_reason_counts[failure_reason] += 1
            failure_file_counts[file_path] += 1
            failure_reasons_by_file[file_path].add(failure_reason)
            failure_gates_by_file[file_path].update(failed_gates)

            failure_item: dict[str, object] = {"file": file_path, "error": error_message}
            if failed_gates:
                failure_item["failed_gates"] = failed_gates
            failures.append(failure_item)
        except Exception as exc:  # pragma: no cover - defensive path
            file_path = str(xml_file)
            failure_reason = "unexpected_error"
            failure_reason_counts[failure_reason] += 1
            failure_file_counts[file_path] += 1
            failure_reasons_by_file[file_path].add(failure_reason)
            failures.append({"file": file_path, "error": f"Unexpected error: {exc}"})

    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "input_dir": str(input_dir),
        "out_dir": str(out_dir),
        "total_xml_files": len(xml_file_paths),
        "reports_written": reports_written,
        "failures": failures,
        "gate_pass_fail_counts": {
            gate_name: gate_counts[gate_name]
            for gate_name in sorted(gate_counts)
        },
        "failure_reason_counts": _sorted_counter(failure_reason_counts),
        "failure_file_counts": _sorted_counter(failure_file_counts),
        "failure_file_leaderboard": _build_failure_file_leaderboard(
            failure_gates_by_file=failure_gates_by_file,
            failure_reasons_by_file=failure_reasons_by_file,
            limit=FAILURE_LEADERBOARD_LIMIT,
        ),
    }
    _write_json_file(summary_out, summary, pretty=args.pretty)

    if failures:
        return 2
    return 0


def run_map_api(args: argparse.Namespace) -> int:
    config = _build_parse_config(args)
    report = parse_xml_file(args.xml_path, config=config)
    mapping_report = generate_api_mapping_artifacts(
        screen=report.screen,
        input_xml_path=args.xml_path,
        out_dir=args.out_dir,
    )
    report_out = Path(args.report_out).resolve()
    _write_json_file(report_out, mapping_report.to_dict(), pretty=args.pretty)

    if mapping_report.summary.mapped_failure > 0:
        return 2
    return 0


def run_gen_ui(args: argparse.Namespace) -> int:
    config = _build_parse_config(args)
    report = parse_xml_file(args.xml_path, config=config)
    ui_report = generate_ui_codegen_artifacts(
        screen=report.screen,
        input_xml_path=args.xml_path,
        out_dir=args.out_dir,
    )
    report_out = Path(args.report_out).resolve()
    _write_json_file(report_out, ui_report.to_dict(), pretty=args.pretty)
    return 0


def run_fidelity_audit(args: argparse.Namespace) -> int:
    config = _build_parse_config(args)
    parse_report = parse_xml_file(args.xml_path, config=config)
    fidelity_report = generate_fidelity_audit_report(
        screen=parse_report.screen,
        input_xml_path=args.xml_path,
        generated_ui_file=args.generated_ui_file,
    )
    report_out = Path(args.report_out).resolve()
    _write_json_file(report_out, fidelity_report.to_dict(), pretty=args.pretty)
    if args.strict:
        enforce_fidelity_audit_strict(fidelity_report)
    return 0


def run_gen_behavior_store(args: argparse.Namespace) -> int:
    config = _build_parse_config(args)
    report = parse_xml_file(args.xml_path, config=config)
    behavior_report = generate_behavior_store_artifacts(
        screen=report.screen,
        input_xml_path=args.xml_path,
        out_dir=args.out_dir,
    )
    report_out = Path(args.report_out).resolve()
    _write_json_file(report_out, behavior_report.to_dict(), pretty=args.pretty)
    return 0


def run_sync_preview(args: argparse.Namespace) -> int:
    report = sync_preview_host(
        generated_screens_dir=args.generated_screens_dir,
        preview_host_dir=args.preview_host_dir,
        manifest_file=args.manifest_file,
        registry_generated_file=args.registry_generated_file,
        pretty=args.pretty,
    )
    if args.report_out:
        report_out = Path(args.report_out).resolve()
        _write_json_file(report_out, report.to_dict(), pretty=args.pretty)
    return 0


def run_prototype_accept(args: argparse.Namespace) -> int:
    threshold_overrides: dict[str, object] = {}
    if args.max_failed_migration_count is not None:
        threshold_overrides["max_failed_migration_count"] = args.max_failed_migration_count
    if args.max_fidelity_risk_count is not None:
        threshold_overrides["max_fidelity_risk_count"] = args.max_fidelity_risk_count
    if args.min_event_runtime_wiring_coverage_ratio is not None:
        threshold_overrides["min_event_runtime_wiring_coverage_ratio"] = (
            args.min_event_runtime_wiring_coverage_ratio
        )
    if args.max_unsupported_event_bindings is not None:
        threshold_overrides["max_unsupported_event_bindings"] = (
            args.max_unsupported_event_bindings
        )
    if args.max_unresolved_transaction_adapter_signals is not None:
        threshold_overrides["max_unresolved_transaction_adapter_signals"] = (
            args.max_unresolved_transaction_adapter_signals
        )

    thresholds = build_prototype_acceptance_thresholds(
        thresholds_file=args.thresholds_file,
        overrides=threshold_overrides,
    )
    report = generate_prototype_acceptance_report(
        args.summary_artifacts,
        thresholds=thresholds,
    )
    report_out = Path(args.report_out).resolve()
    _write_json_file(report_out, report.to_dict(), pretty=args.pretty)
    return 0 if report.verdict == "pass" else 2


def run_migrate_e2e(args: argparse.Namespace) -> int:
    xml_path = Path(args.xml_path).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = _to_report_file_stem(xml_path)
    parse_report_out = (
        Path(args.parse_report_out).resolve()
        if args.parse_report_out
        else out_dir / f"{stem}.parse-report.json"
    )
    map_report_out = (
        Path(args.map_report_out).resolve()
        if args.map_report_out
        else out_dir / f"{stem}.map-api-report.json"
    )
    ui_report_out = (
        Path(args.ui_report_out).resolve()
        if args.ui_report_out
        else out_dir / f"{stem}.gen-ui-report.json"
    )
    fidelity_report_out = (
        Path(args.fidelity_report_out).resolve()
        if args.fidelity_report_out
        else out_dir / f"{stem}.fidelity-audit-report.json"
    )
    preview_report_out = (
        Path(args.preview_report_out).resolve()
        if args.preview_report_out
        else out_dir / f"{stem}.preview-sync-report.json"
    )
    summary_out = (
        Path(args.summary_out).resolve()
        if args.summary_out
        else out_dir / f"{stem}.migration-summary.json"
    )

    stage_status: dict[str, dict[str, object]] = {
        "parse": {"status": "pending"},
        "map_api": {"status": "pending"},
        "gen_ui": {"status": "pending"},
        "fidelity_audit": {"status": "pending"},
        "sync_preview": {"status": "pending"},
    }
    generated_files: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []
    screen_id: str | None = None
    exit_code = 0

    report_files = {
        "parse_report": str(parse_report_out),
        "map_api_report": str(map_report_out),
        "gen_ui_report": str(ui_report_out),
        "fidelity_audit_report": str(fidelity_report_out),
        "preview_sync_report": str(preview_report_out),
        "consolidated_summary": str(summary_out),
    }

    config = _build_parse_config(args)

    try:
        parse_report = parse_xml_file(xml_path, config=config)
    except (ParseStrictError, FileNotFoundError) as exc:
        error_message = str(exc)
        print(error_message, file=sys.stderr)
        stage_status["parse"] = {"status": "failure", "error": error_message}
        stage_status["map_api"] = {"status": "skipped", "reason": "parse_failed"}
        stage_status["gen_ui"] = {"status": "skipped", "reason": "parse_failed"}
        stage_status["fidelity_audit"] = {"status": "skipped", "reason": "parse_failed"}
        stage_status["sync_preview"] = {"status": "skipped", "reason": "parse_failed"}
        errors.append(f"parse: {error_message}")
        exit_code = 2
    else:
        _write_json_file(parse_report_out, parse_report.to_dict(), pretty=args.pretty)
        failed_gates = sorted(gate.name for gate in parse_report.gates if not gate.passed)
        screen_id = parse_report.screen.screen_id
        stage_status["parse"] = {
            "status": "success",
            "report_file": str(parse_report_out),
            "failed_gate_count": len(failed_gates),
            "failed_gates": failed_gates,
            "warning_count": len(parse_report.warnings),
            "error_count": len(parse_report.errors),
        }
        warnings.extend(f"parse: {message}" for message in parse_report.warnings)
        errors.extend(f"parse: {message}" for message in parse_report.errors)

        try:
            map_report = generate_api_mapping_artifacts(
                screen=parse_report.screen,
                input_xml_path=str(xml_path),
                out_dir=args.api_out_dir,
            )
        except Exception as exc:  # pragma: no cover - defensive path
            error_message = f"{type(exc).__name__}: {exc}"
            print(error_message, file=sys.stderr)
            stage_status["map_api"] = {"status": "failure", "error": error_message}
            stage_status["gen_ui"] = {"status": "skipped", "reason": "map_api_exception"}
            stage_status["fidelity_audit"] = {"status": "skipped", "reason": "map_api_exception"}
            stage_status["sync_preview"] = {"status": "skipped", "reason": "map_api_exception"}
            errors.append(f"map_api: {error_message}")
            exit_code = 2
        else:
            _write_json_file(map_report_out, map_report.to_dict(), pretty=args.pretty)
            generated_files.extend([map_report.route_file, map_report.service_file])
            map_stage_failure = map_report.summary.mapped_failure > 0
            stage_status["map_api"] = {
                "status": "failure" if map_stage_failure else "success",
                "report_file": str(map_report_out),
                "route_file": map_report.route_file,
                "service_file": map_report.service_file,
                "total_transactions": map_report.summary.total_transactions,
                "mapped_success": map_report.summary.mapped_success,
                "mapped_failure": map_report.summary.mapped_failure,
                "unsupported": map_report.summary.unsupported,
            }
            warnings.extend(f"map_api: {message}" for message in map_report.warnings)
            if map_stage_failure:
                exit_code = 2
                errors.append(
                    f"map_api: mapping failures detected ({map_report.summary.mapped_failure})"
                )

            try:
                ui_report = generate_ui_codegen_artifacts(
                    screen=parse_report.screen,
                    input_xml_path=str(xml_path),
                    out_dir=args.ui_out_dir,
                )
            except Exception as exc:  # pragma: no cover - defensive path
                error_message = f"{type(exc).__name__}: {exc}"
                print(error_message, file=sys.stderr)
                stage_status["gen_ui"] = {"status": "failure", "error": error_message}
                stage_status["fidelity_audit"] = {"status": "skipped", "reason": "gen_ui_failed"}
                stage_status["sync_preview"] = {"status": "skipped", "reason": "gen_ui_failed"}
                errors.append(f"gen_ui: {error_message}")
                exit_code = 2
            else:
                _write_json_file(ui_report_out, ui_report.to_dict(), pretty=args.pretty)
                generated_files.extend(
                    [
                        ui_report.tsx_file,
                        ui_report.behavior_store_file,
                        ui_report.behavior_actions_file,
                    ]
                )
                stage_status["gen_ui"] = {
                    "status": "success",
                    "report_file": str(ui_report_out),
                    "tsx_file": ui_report.tsx_file,
                    "behavior_store_file": ui_report.behavior_store_file,
                    "behavior_actions_file": ui_report.behavior_actions_file,
                    "behavior_store_hook": ui_report.wiring_contract.behavior_store_hook_name,
                    "total_nodes": ui_report.summary.total_nodes,
                    "rendered_nodes": ui_report.summary.rendered_nodes,
                    "wired_event_bindings": ui_report.summary.wired_event_bindings,
                    "total_event_attributes": ui_report.summary.total_event_attributes,
                    "runtime_wired_event_props": ui_report.summary.runtime_wired_event_props,
                    "unsupported_event_bindings": ui_report.summary.unsupported_event_bindings,
                }
                warnings.extend(f"gen_ui: {message}" for message in ui_report.warnings)

                try:
                    fidelity_report = generate_fidelity_audit_report(
                        screen=parse_report.screen,
                        input_xml_path=str(xml_path),
                        generated_ui_file=ui_report.tsx_file,
                    )
                except Exception as exc:  # pragma: no cover - defensive path
                    error_message = f"{type(exc).__name__}: {exc}"
                    print(error_message, file=sys.stderr)
                    stage_status["fidelity_audit"] = {
                        "status": "failure",
                        "error": error_message,
                    }
                    errors.append(f"fidelity_audit: {error_message}")
                    exit_code = 2
                else:
                    _write_json_file(
                        fidelity_report_out,
                        fidelity_report.to_dict(),
                        pretty=args.pretty,
                    )
                    warnings.extend(
                        f"fidelity_audit: {message}"
                        for message in fidelity_report.warnings
                    )
                    summary = fidelity_report.summary
                    strict_fidelity_failed = (
                        args.strict and fidelity_report.has_blocking_risks()
                    )
                    stage_status["fidelity_audit"] = {
                        "status": "failure" if strict_fidelity_failed else "success",
                        "risk_detected": fidelity_report.has_blocking_risks(),
                        "report_file": str(fidelity_report_out),
                        "missing_node_count": summary.missing_node_count,
                        "extra_generated_node_count": summary.extra_generated_node_count,
                        "position_attribute_total": summary.position_attribute_total,
                        "position_attribute_covered": summary.position_attribute_covered,
                        "style_attribute_total": summary.style_attribute_total,
                        "style_attribute_covered": summary.style_attribute_covered,
                        "position_style_nodes_with_risk": (
                            summary.position_style_nodes_with_risk
                        ),
                    }
                    if fidelity_report.has_blocking_risks():
                        warnings.append(
                            "fidelity_audit: coverage risks detected "
                            f"(missing_nodes={summary.missing_node_count}, "
                            "position_style_nodes_with_risk="
                            f"{summary.position_style_nodes_with_risk})"
                        )
                        if args.strict:
                            try:
                                enforce_fidelity_audit_strict(fidelity_report)
                            except FidelityAuditStrictError as exc:
                                errors.append(f"fidelity_audit: {exc}")
                            exit_code = 2

                generated_screens_dir = Path(args.ui_out_dir).resolve() / "src" / "screens"
                try:
                    preview_report = sync_preview_host(
                        generated_screens_dir=generated_screens_dir,
                        preview_host_dir=args.preview_host_dir,
                        manifest_file=args.manifest_file,
                        registry_generated_file=args.registry_generated_file,
                        pretty=args.pretty,
                    )
                except Exception as exc:  # pragma: no cover - defensive path
                    error_message = f"{type(exc).__name__}: {exc}"
                    print(error_message, file=sys.stderr)
                    stage_status["sync_preview"] = {
                        "status": "failure",
                        "error": error_message,
                        "generated_screens_dir": str(generated_screens_dir),
                    }
                    errors.append(f"sync_preview: {error_message}")
                    exit_code = 2
                else:
                    _write_json_file(
                        preview_report_out,
                        preview_report.to_dict(),
                        pretty=args.pretty,
                    )
                    generated_files.extend(
                        [preview_report.manifest_file, preview_report.registry_generated_file]
                    )
                    stage_status["sync_preview"] = {
                        "status": "success",
                        "report_file": str(preview_report_out),
                        "manifest_file": preview_report.manifest_file,
                        "registry_generated_file": preview_report.registry_generated_file,
                        "generated_screen_count": preview_report.generated_screen_count,
                        "generated_entry_modules": preview_report.generated_entry_modules,
                    }
                    warnings.extend(
                        f"sync_preview: {message}" for message in preview_report.warnings
                    )

    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "command": MIGRATE_E2E_COMMAND_NAME,
        "input_xml_path": str(xml_path),
        "screen_id": screen_id,
        "overall_status": "success" if exit_code == 0 else "failure",
        "overall_exit_code": exit_code,
        "reports": report_files,
        "stages": stage_status,
        "generated_file_references": _dedupe_preserve_order(generated_files),
        "warnings": warnings,
        "errors": errors,
    }
    _write_json_file(summary_out, summary, pretty=args.pretty)
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "parse":
            return run_parse(args)
        if args.command == "batch-parse":
            return run_batch_parse(args)
        if args.command == "map-api":
            return run_map_api(args)
        if args.command == "gen-ui":
            return run_gen_ui(args)
        if args.command == "fidelity-audit":
            return run_fidelity_audit(args)
        if args.command == "gen-behavior-store":
            return run_gen_behavior_store(args)
        if args.command == "sync-preview":
            return run_sync_preview(args)
        if args.command == PROTOTYPE_ACCEPT_COMMAND_NAME:
            return run_prototype_accept(args)
        if args.command == MIGRATE_E2E_COMMAND_NAME:
            return run_migrate_e2e(args)
    except ParseStrictError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except FidelityAuditStrictError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"File not found: {exc}", file=sys.stderr)
        return 2

    print(f"Unsupported command: {args.command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
