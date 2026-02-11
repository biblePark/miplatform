# Code Style and Repository Standards

## 1) General

- Prefer clarity over brevity.
- Keep functions small and deterministic.
- Avoid hidden side effects.
- Use explicit error messages with actionable context.

## 2) Python (Migrator Core)

- Target version: `Python 3.12+`.
- Use type hints on public interfaces.
- Use dataclass or pydantic-style models for stable IR contracts.
- Parser and validator modules must be pure as much as possible.
- IO and side effects should stay in orchestration layers.

## 3) TypeScript/React (Generated Frontend)

- Generated code should be predictable and lint-friendly.
- Separate view rendering, state wiring, and event wiring.
- Keep component naming deterministic from source screen/component ids.
- Preserve source references in comments or metadata fields.

## 4) JavaScript/Express (Generated API)

- Keep route and service layers separate.
- Do not embed SQL directly in route handlers.
- Transaction mapping must include source references.

## 5) Naming Conventions

- Files: `snake_case` for Python, `kebab-case` for docs, `PascalCase` for React components, `camelCase` for JS/TS variables.
- Branches: `codex/r<round-number>-<scope>`.
- Reports: `/generated/reports/r<round-number>/...`.

## 6) Testing Standards

- Every new parser rule requires unit tests.
- Every new mapping rule requires at least one golden test fixture.
- Regression tests must be added for discovered edge cases.

## 7) Documentation Updates

When behavior, rules, or architecture changes:

- Update relevant `docs/*.md`.
- Add an item to `/docs/DECISION_LOG.md`.
- Add a round entry in `/docs/ROUND_HISTORY.md`.

