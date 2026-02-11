#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _to_bullets(items: list[str]) -> str:
    if not items:
        return "- (none)"
    return "\n".join(f"- {item}" for item in items)


def _render_template(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="render_subagent_briefs",
        description="Render per-lane markdown briefs from round JSON config",
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to round config JSON (see ops/subagents/example_round_r04.json)",
    )
    parser.add_argument(
        "--template",
        default="docs/multi-agent/SUBAGENT_TASK_TEMPLATE.md",
        help="Path to markdown template",
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        help="Output directory for generated lane briefs",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config_path = Path(args.config).resolve()
    template_path = Path(args.template).resolve()
    out_dir = Path(args.out_dir).resolve()

    config = _load_json(config_path)
    template = template_path.read_text(encoding="utf-8")
    round_id = config.get("round_id", "RXX")
    base_branch = config.get("base_branch", "main")
    default_checks = config.get("default_checks", [])
    lanes = config.get("lanes", [])

    out_dir.mkdir(parents=True, exist_ok=True)
    created = 0

    for lane in lanes:
        lane_name = str(lane.get("name", "lane"))
        values = {
            "ROUND_ID": round_id,
            "LANE_NAME": lane_name,
            "BRANCH_NAME": str(
                lane.get("branch_name", f"codex/{round_id.lower()}-{lane_name}")
            ),
            "WORKTREE_PATH": str(lane.get("worktree_path", f"/tmp/miflatform-{lane_name}")),
            "BASE_BRANCH": base_branch,
            "LANE_OBJECTIVE": str(lane.get("objective", "(objective not set)")),
            "DELIVERABLES_LIST": _to_bullets(list(lane.get("deliverables", []))),
            "REQUIRED_CHECKS_LIST": _to_bullets(
                list(lane.get("checks", [])) or list(default_checks)
            ),
        }
        rendered = _render_template(template, values)
        out_file = out_dir / f"{lane_name}.md"
        out_file.write_text(rendered, encoding="utf-8")
        created += 1

    print(f"Generated {created} brief files in {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

