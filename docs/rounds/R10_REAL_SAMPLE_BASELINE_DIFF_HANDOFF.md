# R10 Real-Sample Baseline Diff Handoff

## Lane Info

- Round: `R10`
- Lane: `real-sample-baseline-diff`
- Branch: `codex/r10-real-sample-baseline-diff`
- Worktree: `/tmp/miflatform-r10-real-sample-baseline-diff`

## Summary

- Implemented:
- Added `scripts/real_sample_baseline.py` with deterministic `snapshot` and `diff` workflows for real-sample regression baseline management.
- Added KPI tolerance gate support for strict regression failure (`diff --strict`) with configured thresholds.
- Added default tolerance config at `ops/real_sample_baseline_tolerances.json`.
- Added unit coverage in `tests/test_real_sample_baseline.py` for snapshot persistence, stage/risk delta classification, and strict tolerance pass/fail behavior.
- Updated `README.md` and `USER_MANUAL.md` with baseline lifecycle, artifact paths, and strict gate usage.
- Not implemented:
- Automated sample-set hash mismatch hard-fail behavior (currently surfaced in diff metadata/report; no automatic gate failure).

## Changed Files

- `README.md`
- `USER_MANUAL.md`
- `ops/real_sample_baseline_tolerances.json`
- `scripts/real_sample_baseline.py`
- `tests/test_real_sample_baseline.py`
- `docs/rounds/R10_REAL_SAMPLE_BASELINE_DIFF_HANDOFF.md`

## Commands Run

- `python3 -m unittest tests.test_real_sample_baseline -v`
- Result: Passed (`Ran 4 tests`, `OK`)

- `python3 -m unittest discover -s tests -p 'test_*.py' -v`
- Result: Passed (`Ran 55 tests`, `OK`)

## Validation Status

- Required checks passed: Yes (`python3 -m unittest discover -s tests -p 'test_*.py' -v`)
- Required checks failed: None

## Open Risks / Follow-Ups

- Diff strict gate assumes KPI comparability across rounds; if sample set changes, results can be noisy. Sample hash/count are reported, but automatic mismatch fail policy is not yet enforced.
- Tolerance config is intentionally conservative (mostly zero tolerance). Teams may need to tune `ops/real_sample_baseline_tolerances.json` for operational noise.

## Merge Notes for PM

- Safe merge order suggestion: merge this lane after/with any lane editing real-sample regression docs to reduce `README.md`/`USER_MANUAL.md` conflicts.
- Conflict-prone files: `README.md`, `USER_MANUAL.md`
