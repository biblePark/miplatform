# Subagent Handoff

## Lane Info

- Round: `R08`
- Lane: `runtime-behavior-wiring`
- Branch: `codex/r08-runtime-behavior-wiring`
- Worktree: `/tmp/miflatform-r08-runtime-behavior-wiring`

## Summary

- Implemented:
- Added deterministic runtime wiring contract module at `src/migrator/runtime_wiring.py` and reused it in both UI and behavior-store codegen paths.
- Extended behavior-store codegen to emit explicit event-to-action binding metadata (`event_action_bindings` in report + `screenBehaviorEventActionBindings` in actions module).
- Updated UI codegen to:
- generate runtime-wired imports/hooks to behavior store (`use<Screen>BehaviorStore`)
- wire supported XML `on*` attributes to React event props with duplicate-safe action names
- emit behavior store/actions artifacts alongside TSX output to keep generated imports resolvable.
- Extended migrate-e2e summary wiring metadata in `gen_ui` stage and generated-file references to include behavior files.
- Added/updated tests for deterministic wiring artifacts, duplicate-safe naming integration, and CLI summary/report changes.
- Updated `README.md`, `USER_MANUAL.md`, and `docs/TECH_SPEC.md` for R08 runtime wiring behavior.
- Not implemented:
- Full XML event-to-React prop parity for every possible `on*` attribute (limited to mapped core events in `_EVENT_ATTR_TO_REACT_PROP`).

## Changed Files

- `src/migrator/runtime_wiring.py` (new)
- `src/migrator/behavior_store_codegen.py`
- `src/migrator/ui_codegen.py`
- `src/migrator/cli.py`
- `src/migrator/__init__.py`
- `tests/test_behavior_store_codegen.py`
- `tests/test_ui_codegen.py`
- `tests/test_cli.py`
- `README.md`
- `USER_MANUAL.md`
- `docs/TECH_SPEC.md`
- `docs/rounds/R08_RUNTIME_BEHAVIOR_WIRING_HANDOFF.md` (this file)

## Commands Run

- `python3 -m unittest tests/test_behavior_store_codegen.py tests/test_ui_codegen.py tests/test_cli.py -v`
- Result:
- Passed (`Ran 17 tests`, `OK`)

- `python3 -m unittest discover -s tests -p 'test_*.py' -v`
- Result:
- Passed (`Ran 38 tests`, `OK`)

- `cd preview-host && npm run build`
- Result:
- Initial failure: `sh: tsc: command not found` (dependencies not installed in worktree)

- `cd preview-host && npm install`
- Result:
- Passed (`added 73 packages`, `0 vulnerabilities`)

- `cd preview-host && npm run build`
- Result:
- Passed (`vite build` complete)

## Validation Status

- Required checks passed:
- `python3 -m unittest discover -s tests -p 'test_*.py' -v`
- `cd preview-host && npm run build` (after installing dependencies)
- Required checks failed:
- None

## Open Risks / Follow-Ups

- Event wiring currently maps only explicitly supported event attributes in `_EVENT_ATTR_TO_REACT_PROP`; unsupported `on*` attributes emit trace metadata and warning but no React handler prop.
- `gen-ui` now emits behavior files as part of UI generation (to keep runtime imports resolvable); behavior-only pipelines should continue using `gen-behavior-store` where explicit behavior-only generation is desired.

## Merge Notes for PM

- Safe merge order suggestion:
- Merge this lane before/with any lane modifying `src/migrator/ui_codegen.py`, `src/migrator/behavior_store_codegen.py`, or `tests/test_cli.py` to reduce contract drift.
- Conflict-prone files:
- `src/migrator/ui_codegen.py`
- `src/migrator/behavior_store_codegen.py`
- `src/migrator/cli.py`
- `tests/test_cli.py`
