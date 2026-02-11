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
- Round 1: Parser bootstrap created with strict gate plumbing, IR dataclasses, CLI, and tests.

## Round 1 Quick Start

Run tests:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Run parser CLI on fixture:

```bash
PYTHONPATH=src python3 -m migrator parse tests/fixtures/simple_screen.xml --out out/parse-report.json --pretty
```

Run strict parse with profiles:

```bash
PYTHONPATH=src python3 -m migrator parse tests/fixtures/simple_screen.xml --out out/parse-report-strict.json --strict --known-tags-file tests/fixtures/known_tags_all.txt --known-attrs-file tests/fixtures/known_attrs_all.json --pretty
```

## Round 1 Scope

Round 1 establishes parser execution baseline only:

- `pyproject.toml` with Python package entrypoint (`mifl-migrator`).
- `src/migrator/models.py` for base IR and validation gate structures.
- `src/migrator/parser.py` for strict parser bootstrap.
- `src/migrator/cli.py` for parse command and JSON report output.
- `tests/` fixtures and smoke/strict tests.

Code generation and runtime fidelity tooling are planned for subsequent rounds.
