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

- `/USER_MANUAL.md`: End-user guide (Korean) for input placement, command execution, and result verification.
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
- Round 5: API mapping scaffold + preview host scaffold + batch summary aggregation.
- Round 6: UI TSX scaffold generation + preview manifest/registry sync.
- Round 7: One-command end-to-end migration orchestration with consolidated summary report.
- Round 8: Runtime wiring contract + real-sample migrate-e2e regression automation with extraction/mapping/fidelity risk trend reporting.
- Round 9: Deterministic XML-to-generated-UI fidelity audit module/report with strict audit gates and migrate-e2e integration.

## Quick Start

Run tests:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Run strict parse on one XML:

```bash
PYTHONPATH=src python3 -m migrator parse tests/fixtures/simple_screen_fixture.txt --out out/parse-report.json --strict --capture-text --known-tags-file tests/fixtures/known_tags_all.txt --known-attrs-file tests/fixtures/known_attrs_all.json --pretty
```

Run batch parse:

```bash
PYTHONPATH=src python3 -m migrator batch-parse tests/fixtures --out-dir out/batch-reports --summary-out out/batch-summary.json --recursive --strict --capture-text --known-tags-file tests/fixtures/known_tags_all.txt --known-attrs-file tests/fixtures/known_attrs_all.json --pretty
```

Run API mapping scaffold generation:

```bash
PYTHONPATH=src python3 -m migrator map-api tests/fixtures/simple_screen_fixture.txt --out-dir out/generated-api --report-out out/map-api-report.json --strict --capture-text --known-tags-file tests/fixtures/known_tags_all.txt --known-attrs-file tests/fixtures/known_attrs_all.json --pretty
```

Run behavior store/action scaffold generation:

```bash
PYTHONPATH=src python3 -m migrator gen-behavior-store tests/fixtures/simple_screen_fixture.txt --out-dir out/generated-frontend --report-out out/gen-behavior-store-report.json --strict --capture-text --known-tags-file tests/fixtures/known_tags_all.txt --known-attrs-file tests/fixtures/known_attrs_all.json --pretty
```

Run fidelity audit against generated UI TSX:

```bash
PYTHONPATH=src python3 -m migrator fidelity-audit tests/fixtures/simple_screen_fixture.txt --generated-ui-file generated/frontend/src/screens/simple-screen-fixture.tsx --report-out out/fidelity-audit-report.json --strict --capture-text --known-tags-file tests/fixtures/known_tags_all.txt --known-attrs-file tests/fixtures/known_attrs_all.json --pretty
```

Run one-command end-to-end migration orchestration:

```bash
PYTHONPATH=src python3 -m migrator migrate-e2e tests/fixtures/simple_screen_fixture.txt --out-dir out/e2e --api-out-dir generated/api --ui-out-dir generated/frontend --preview-host-dir preview-host --strict --capture-text --known-tags-file tests/fixtures/known_tags_all.txt --known-attrs-file tests/fixtures/known_attrs_all.json --pretty
```

This command executes parse/map-api/gen-ui/fidelity-audit/sync-preview in sequence and writes:

- Stage reports under `out/e2e` (default): parse/map-api/gen-ui/fidelity-audit/sync-preview JSON
- Generated UI stage outputs: `src/screens/*.tsx` plus deterministic runtime-wired `src/behavior/*.store.ts` and `src/behavior/*.actions.ts`
- Consolidated summary report: `out/e2e/<xml-stem>.migration-summary.json`
- Summary includes stage statuses, report file references, and generated file references for verification

Run real-sample migrate-e2e regression across a sample set:

```bash
PYTHONPATH=src python3 scripts/run_real_sample_e2e_regression.py --samples-dir data/input/xml --recursive --out-dir out/real-sample-e2e-regression --strict --capture-text --known-tags-file data/input/profiles/known_tags.txt --known-attrs-file data/input/profiles/known_attrs.json --pretty
```

This command runs `migrate-e2e` for each XML in the sample set and writes:

- Consolidated regression summary JSON: `out/real-sample-e2e-regression/regression-summary.json`
- Consolidated regression summary Markdown: `out/real-sample-e2e-regression/regression-summary.md`
- Per-sample stage reports and generated artifacts under `out/real-sample-e2e-regression/runs/<index>-<xml-stem>/`
- Summary includes success/failure totals, stage-level failure counts/details, top warnings, extraction/mapping/fidelity risk trends, and unresolved malformed/XML blockers

Sync generated UI screens into preview-host manifest + registry:

```bash
PYTHONPATH=src python3 -m migrator sync-preview --generated-screens-dir generated/frontend/src/screens --preview-host-dir preview-host --report-out out/preview-sync-report.json --pretty
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

## Implemented Scope (R01-R07)

- Parser, validator, canonicalizer, and CLI pipeline under `src/migrator/`.
- Unit tests for parser/validator/CLI under `tests/`.
- API mapping scaffold generator under `src/migrator/api_mapping.py`.
- Preview host scaffold under `preview-host/` and manifest validator under `src/migrator/preview_manifest.py`.
- Preview manifest/registry sync utility under `src/migrator/preview_sync.py`.
- End-to-end orchestration CLI (`migrate-e2e`) with consolidated migration summary report.
- Deterministic runtime wiring contract module (`src/migrator/runtime_wiring.py`) used by both `gen-ui` and `gen-behavior-store`.
- Real-sample regression runner (`scripts/run_real_sample_e2e_regression.py`) with consolidated risk trend reporting.
- Multi-agent templates under `docs/multi-agent/`.
- Subagent config examples under `ops/subagents/`.
- Parallel setup and brief rendering scripts under `scripts/`.

Code generation and runtime fidelity tooling are planned for subsequent rounds.
