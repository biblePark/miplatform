from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

from .models import ParseConfig
from .parser import ParseStrictError, parse_xml_file

STRICT_GATE_FAILURE_PREFIX = "Strict parse failed for gates:"
XML_PARSE_FAILURE_PREFIX = "XML parse failure:"
FAILURE_LEADERBOARD_LIMIT = 10


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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "parse":
            return run_parse(args)
        if args.command == "batch-parse":
            return run_batch_parse(args)
    except ParseStrictError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"File not found: {exc}", file=sys.stderr)
        return 2

    print(f"Unsupported command: {args.command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
