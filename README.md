# MIPLATFORM Migrator

Migration toolkit for legacy MIPLATFORM XML applications into:

- Frontend: `Vite + React 19 + MUI v7 + Zustand`
- API: `Express (JavaScript)`
- Migrator engine: `Python`

This repository is operated as a multi-threaded, round-based project using `git worktree`.

## Project Priorities

- Parse legacy XML without loss.
- Prove parse completeness with measurable validation gates.
- Preserve UI shape and behavior as faithfully as possible.
- Keep generated output traceable back to original XML lines and nodes.

## Documentation Map

- `/docs/PROJECT_RULES.md`: Non-negotiable engineering and migration rules.
- `/docs/PROJECT_CONTEXT.md`: Domain context, constraints, goals, and assumptions.
- `/docs/TECH_SPEC.md`: Core architecture and validation design.
- `/docs/CODE_STYLE.md`: Code and repository style standards.
- `/docs/WORKTREE_RUNBOOK.md`: Multi-threaded round workflow with `git worktree`.
- `/docs/multi-agent/README.md`: Templates and workflow for subagent coordination.
- `/docs/ROUND_HISTORY.md`: Execution history by round.
- `/docs/ROUND_TEMPLATE.md`: Template for adding a new round entry.
- `/docs/DECISION_LOG.md`: ADR-style decision records.

## Current Implementation Status

- Round 0: Governance and process baseline created.
- Round 1: Parser bootstrap with strict tag/attr gates and CLI.
- Round 2: Roundtrip validator + Dataset/Binding/Event IR extraction + coverage gates.
- Round 3: Transaction/Script extraction + canonical hash gate + batch parse CLI.
- Round 4: Multi-agent operation pack (subagent templates + lane setup/brief scripts).

## Quick Start

Run tests:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Run strict parse on one XML:

```bash
PYTHONPATH=src python3 -m migrator parse tests/fixtures/simple_screen.xml --out out/parse-report.json --strict --capture-text --known-tags-file tests/fixtures/known_tags_all.txt --known-attrs-file tests/fixtures/known_attrs_all.json --pretty
```

Run batch parse:

```bash
PYTHONPATH=src python3 -m migrator batch-parse tests/fixtures --out-dir out/batch-reports --summary-out out/batch-summary.json --recursive --strict --capture-text --known-tags-file tests/fixtures/known_tags_all.txt --known-attrs-file tests/fixtures/known_attrs_all.json --pretty
```

Example `out/batch-summary.json` (trimmed):

```json
{
  "generated_at_utc": "2026-02-11T00:00:00+00:00",
  "input_dir": "/abs/path/tests/fixtures",
  "out_dir": "/abs/path/out/batch-reports",
  "total_xml_files": 3,
  "reports_written": 1,
  "failures": [
    {
      "file": "/abs/path/tests/fixtures/strict_fail.xml",
      "error": "Strict parse failed for gates: unknown_tag_count",
      "failed_gates": ["unknown_tag_count"]
    },
    {
      "file": "/abs/path/tests/fixtures/broken.xml",
      "error": "XML parse failure: mismatched tag: line 3, column 2"
    }
  ],
  "gate_pass_fail_counts": {
    "unknown_tag_count": { "pass_count": 1, "fail_count": 1 },
    "canonical_roundtrip_hash_match": { "pass_count": 2, "fail_count": 0 }
  },
  "failure_reason_counts": {
    "strict_gate_failure": 1,
    "xml_parse_failure": 1
  },
  "failure_file_counts": {
    "/abs/path/tests/fixtures/strict_fail.xml": 1,
    "/abs/path/tests/fixtures/broken.xml": 1
  },
  "failure_file_leaderboard": [
    {
      "file": "/abs/path/tests/fixtures/strict_fail.xml",
      "failed_gate_count": 1,
      "failed_gates": ["unknown_tag_count"],
      "failure_reasons": ["strict_gate_failure"]
    },
    {
      "file": "/abs/path/tests/fixtures/broken.xml",
      "failed_gate_count": 0,
      "failed_gates": [],
      "failure_reasons": ["xml_parse_failure"]
    }
  ]
}
```

Generate subagent briefs from config:

```bash
scripts/render_subagent_briefs.py --config ops/subagents/example_round_r04.json --out-dir out/subagent-briefs-r04
```

Preview parallel lane worktrees without creating them:

```bash
scripts/setup_round_parallel.sh --dry-run r04 main api-mapping ui-preview
```

Create parallel lane worktrees:

```bash
scripts/setup_round_parallel.sh r04 main api-mapping ui-preview
```

## Implemented Scope (R01-R04)

- Parser, validator, canonicalizer, and CLI pipeline under `src/migrator/`.
- Unit tests for parser/validator/CLI under `tests/`.
- Multi-agent templates under `docs/multi-agent/`.
- Subagent config examples under `ops/subagents/`.
- Parallel setup and brief rendering scripts under `scripts/`.

Code generation and runtime fidelity tooling are planned for subsequent rounds.
