# R05 Kickoff

## Round Metadata

- Round ID: `R05`
- Date: `2026-02-11`
- Base branch: `main`
- Round kickoff branch: `codex/r05-round-kickoff`

## Scope

Execute R05 as a parallel multi-lane round to move from validated parser outputs to executable migration artifacts.

## Lanes

| Lane | Branch | Worktree | Focus |
|---|---|---|---|
| `api-mapping` | `codex/r05-api-mapping` | `/tmp/miflatform-r05-api-mapping` | TransactionIR -> Express route/service mapping scaffold |
| `ui-preview-host` | `codex/r05-ui-preview-host` | `/tmp/miflatform-r05-ui-preview-host` | Vite preview host and manifest loader scaffold |
| `report-aggregation` | `codex/r05-report-aggregation` | `/tmp/miflatform-r05-report-aggregation` | Batch summary aggregation and gate leaderboard |

## Global Gates

- `python3 -m unittest discover -s tests -p 'test_*.py' -v`
- Existing strict parse and canonical validation paths remain green.
- Lane handoff templates completed for all lanes.

## Dispatch Procedure

1. Generate subagent briefs:
2. `scripts/render_subagent_briefs.py --config ops/subagents/round_r05.json --out-dir out/subagent-briefs-r05`
3. Create lane worktrees:
4. `scripts/setup_round_parallel.sh r05 main api-mapping ui-preview-host report-aggregation`
5. Dispatch each brief in `out/subagent-briefs-r05/`.
6. Collect handoffs and merge by `/docs/multi-agent/PM_MERGE_CHECKLIST.md`.

## Notes

- This kickoff document is committed first so all lane branches inherit the same source-of-truth scope.
- Any scope change during execution must update this file and corresponding lane briefs.
