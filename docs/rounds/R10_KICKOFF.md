# R10 Kickoff

## Round Metadata

- Round ID: `R10`
- Date: `2026-02-12`
- Base branch: `main`
- Round kickoff branch: `codex/r10-round-kickoff`

## Scope

Execute R10 as a parallel prototype-acceptance round to convert current migration outputs into an auditable pass/fail prototype review workflow.

## Lanes

| Lane | Branch | Worktree | Focus |
|---|---|---|---|
| `prototype-acceptance-gates` | `codex/r10-prototype-acceptance-gates` | `/tmp/miflatform-r10-prototype-acceptance-gates` | Implement KPI-driven prototype acceptance command/report |
| `real-sample-baseline-diff` | `codex/r10-real-sample-baseline-diff` | `/tmp/miflatform-r10-real-sample-baseline-diff` | Add baseline snapshot + delta reporting for real-sample regression outputs |
| `preview-host-prototype-smoke` | `codex/r10-preview-host-prototype-smoke` | `/tmp/miflatform-r10-preview-host-prototype-smoke` | Add repeatable preview-host smoke evidence for generated screen route/module readiness |

## Global Gates

- `python3 -m unittest discover -s tests -p 'test_*.py' -v`
- `cd preview-host && npm run build`
- For user-visible command/flow changes, update `/Users/biblepark/Desktop/works/miflatform-migrator/USER_MANUAL.md` in the same round.
- All lane handoff files are completed.

## Dispatch Procedure

1. Generate subagent briefs:
2. `scripts/render_subagent_briefs.py --config ops/subagents/round_r10.json --out-dir out/subagent-briefs-r10`
3. Create lane worktrees:
4. `scripts/setup_round_parallel.sh r10 main prototype-acceptance-gates real-sample-baseline-diff preview-host-prototype-smoke`
5. Dispatch each brief in `out/subagent-briefs-r10/`.
6. Collect handoffs and merge by `/docs/multi-agent/PM_MERGE_CHECKLIST.md`.

## Notes

- R10 is the prototype-acceptance round; expected output is a repeatable go/no-go report rather than only raw generation artifacts.
- Generated migration inputs/outputs remain non-versioned (`.gitignore` policy).
