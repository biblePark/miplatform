from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

from .models import ParseConfig
from .parser import ParseStrictError, parse_xml_file


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

    pattern = "**/*.xml" if args.recursive else "*.xml"
    xml_files = sorted(input_dir.glob(pattern))

    reports_written = 0
    failures: list[dict[str, str]] = []

    for xml_file in xml_files:
        if not xml_file.is_file():
            continue

        try:
            report = parse_xml_file(xml_file, config=config)
            relative = xml_file.relative_to(input_dir)
            report_path = out_dir / relative.with_suffix(".json")
            _write_json_file(report_path, report.to_dict(), pretty=args.pretty)
            reports_written += 1
        except ParseStrictError as exc:
            failures.append({"file": str(xml_file), "error": str(exc)})
        except Exception as exc:  # pragma: no cover - defensive path
            failures.append({"file": str(xml_file), "error": f"Unexpected error: {exc}"})

    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "input_dir": str(input_dir),
        "out_dir": str(out_dir),
        "total_xml_files": len([p for p in xml_files if p.is_file()]),
        "reports_written": reports_written,
        "failures": failures,
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
