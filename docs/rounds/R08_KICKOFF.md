# R08 Kickoff

## Round Metadata

- Round ID: `R08`
- Date: `2026-02-11`
- Base branch: `main`
- Round kickoff branch: `codex/r08-round-kickoff`

## Scope

Execute R08 as a parallel implementation round to connect generated UI/behavior scaffolds at runtime and strengthen real-sample verification confidence.

## Lanes

| Lane | Branch | Worktree | Focus |
|---|---|---|---|
| `ui-layout-fidelity-pass` | `codex/r08-ui-layout-fidelity-pass` | `/tmp/miflatform-r08-ui-layout-fidelity-pass` | Improve generated UI layout/style fidelity for core controls and container positioning |
| `runtime-behavior-wiring` | `codex/r08-runtime-behavior-wiring` | `/tmp/miflatform-r08-runtime-behavior-wiring` | Wire generated UI outputs to generated Zustand behavior store/actions with deterministic contracts |
| `real-sample-e2e-regression` | `codex/r08-real-sample-e2e-regression` | `/tmp/miflatform-r08-real-sample-e2e-regression` | Run/automate real XML sample `migrate-e2e` regression and produce quality summary artifacts |

## Global Gates

- `python3 -m unittest discover -s tests -p 'test_*.py' -v`
- `cd preview-host && npm run build`
- For user-visible command/flow changes, update `/Users/biblepark/Desktop/works/miflatform-migrator/USER_MANUAL.md` in the same round.
- All lane handoff files are completed.

## Dispatch Procedure

1. Generate subagent briefs:
2. `scripts/render_subagent_briefs.py --config ops/subagents/round_r08.json --out-dir out/subagent-briefs-r08`
3. Create lane worktrees:
4. `scripts/setup_round_parallel.sh r08 main ui-layout-fidelity-pass runtime-behavior-wiring real-sample-e2e-regression`
5. Dispatch each brief in `out/subagent-briefs-r08/`.
6. Collect handoffs and merge by `/docs/multi-agent/PM_MERGE_CHECKLIST.md`.

## Notes

- R08 should preserve R07 commands (`gen-ui`, `gen-behavior-store`, `migrate-e2e`) and extend integration quality.
- Generated migration inputs/outputs remain non-versioned (`.gitignore` policy).
