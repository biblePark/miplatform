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
- `/docs/ROUND_HISTORY.md`: Execution history by round.
- `/docs/ROUND_TEMPLATE.md`: Template for adding a new round entry.
- `/docs/DECISION_LOG.md`: ADR-style decision records.

## Current Implementation Status

- Round 0: Governance and process baseline created.
- Round 1: Parser bootstrap with strict tag/attr gates and CLI.
- Round 2: Roundtrip validator + Dataset/Binding/Event IR extraction + extraction coverage gates.

## Quick Start

Run tests:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Run parser CLI on fixture:

```bash
PYTHONPATH=src python3 -m migrator parse tests/fixtures/simple_screen.xml --out out/parse-report.json --pretty
```

Run strict parse with known profiles:

```bash
PYTHONPATH=src python3 -m migrator parse tests/fixtures/simple_screen.xml --out out/parse-report-strict.json --strict --known-tags-file tests/fixtures/known_tags_all.txt --known-attrs-file tests/fixtures/known_attrs_all.json --pretty
```

Optional: disable roundtrip gate for diagnosis:

```bash
PYTHONPATH=src python3 -m migrator parse tests/fixtures/simple_screen.xml --out out/parse-report-no-roundtrip.json --disable-roundtrip-gate --pretty
```

## Implemented Scope (R01-R02)

- `pyproject.toml` with Python package entrypoint (`mifl-migrator`).
- `src/migrator/models.py` with base AST and extraction IR models.
- `src/migrator/parser.py` with strict parser + extraction + gate evaluation.
- `src/migrator/validator.py` with structural roundtrip diff engine.
- `src/migrator/cli.py` parse command and JSON report output.
- `tests/` fixtures and parser/validator unit tests.

Code generation and runtime fidelity tooling are planned for subsequent rounds.
