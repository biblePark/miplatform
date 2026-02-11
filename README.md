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

## Round 0 Scope

Round 0 establishes governance and execution scaffolding only.
No parser/codegen implementation is included yet.

