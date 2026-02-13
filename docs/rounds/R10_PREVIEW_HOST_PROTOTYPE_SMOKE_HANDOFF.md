# Subagent Handoff

## Lane Info

- Round: `R10`
- Lane: `preview-host-prototype-smoke`
- Branch: `codex/r10-preview-host-prototype-smoke`
- Worktree: `/tmp/miflatform-r10-preview-host-prototype-smoke`

## Summary

- Implemented:
  - Added new `preview-smoke` CLI command to validate generated preview screen module readiness and emit evidence JSON.
  - Added deterministic smoke evidence artifact fields: generated `screens[]`, `route_paths[]`, and `unresolved_module_count`.
  - Integrated smoke evidence into `migrate-e2e` as `preview_smoke` stage with report output and failure propagation when unresolved modules exist.
  - Added unit tests for smoke module and CLI integration, plus `migrate-e2e` summary assertions for smoke stage/report.
  - Updated user-facing docs (`README.md`, `USER_MANUAL.md`, `preview-host/README.md`) for smoke execution and interpretation.
- Not implemented:
  - No separate baseline/history diff for smoke artifacts (out of this lane scope).

## Changed Files

- `src/migrator/preview_smoke.py`
- `src/migrator/cli.py`
- `src/migrator/__init__.py`
- `tests/test_preview_smoke.py`
- `tests/test_cli.py`
- `README.md`
- `USER_MANUAL.md`
- `preview-host/README.md`

## Commands Run

- `python3 -m unittest tests.test_preview_smoke tests.test_cli -v`
- Result:
  - Passed (`Ran 16 tests`, `OK`)

- `python3 -m unittest discover -s tests -p 'test_*.py' -v`
- Result:
  - Passed (`Ran 55 tests`, `OK`)

- `cd preview-host && npm run build`
- Result:
  - First run failed (`tsc: command not found`) because `preview-host` dependencies were not installed in this worktree.

- `cd preview-host && npm install`
- Result:
  - Passed (`added 73 packages`, `0 vulnerabilities`)

- `cd preview-host && npm run build`
- Result:
  - Passed (Vite production build completed successfully)

## Validation Status

- Required checks passed:
  - `python3 -m unittest discover -s tests -p 'test_*.py' -v`
  - `cd preview-host && npm run build`
- Required checks failed:
  - None (after installing `preview-host` dependencies)

## Open Risks / Follow-Ups

- `preview-smoke` currently validates generated manifest entries (`entryModule` prefix `screens/generated/`) by design; manual placeholder entries remain outside unresolved-module counting.
- `preview-smoke` report path in `migrate-e2e` is currently fixed to `out/e2e/<xml-stem>.preview-smoke-report.json` (no explicit override flag yet).

## Merge Notes for PM

- Safe merge order suggestion:
  - Merge after/beside other R10 lanes; this lane is mostly additive and low conflict outside shared docs/CLI.
- Conflict-prone files:
  - `src/migrator/cli.py`
  - `tests/test_cli.py`
  - `README.md`
  - `USER_MANUAL.md`
