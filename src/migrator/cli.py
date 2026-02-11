from __future__ import annotations

import argparse
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mifl-migrator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_cmd = subparsers.add_parser("parse", help="Parse one XML file into IR/report JSON")
    parse_cmd.add_argument("xml_path", help="Path to source XML file")
    parse_cmd.add_argument("--out", required=True, help="Output JSON report path")
    parse_cmd.add_argument("--strict", action="store_true", help="Fail when validation gates fail")
    parse_cmd.add_argument("--capture-text", action="store_true", help="Capture node text bodies")
    parse_cmd.add_argument(
        "--known-tags-file",
        help="Optional newline-delimited tag list used for unknown-tag gate",
    )
    parse_cmd.add_argument(
        "--known-attrs-file",
        help="Optional JSON map: {\"TagName\": [\"attr1\"], \"*\": [\"globalAttr\"]}",
    )
    parse_cmd.add_argument(
        "--disable-roundtrip-gate",
        action="store_true",
        help="Disable roundtrip structural diff gate",
    )
    parse_cmd.add_argument("--pretty", action="store_true", help="Pretty-print output JSON")

    return parser


def run_parse(args: argparse.Namespace) -> int:
    config = ParseConfig(
        strict=args.strict,
        known_tags=_load_known_tags(args.known_tags_file),
        known_attrs_by_tag=_load_known_attrs(args.known_attrs_file),
        capture_text=args.capture_text,
        enable_roundtrip_gate=not args.disable_roundtrip_gate,
    )
    report = parse_xml_file(args.xml_path, config=config)

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    out_path.write_text(
        json.dumps(payload, indent=2 if args.pretty else None, ensure_ascii=False),
        encoding="utf-8",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "parse":
        try:
            return run_parse(args)
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
