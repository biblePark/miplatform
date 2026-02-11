# R07 Kickoff

## Round Metadata

- Round ID: `R07`
- Date: `2026-02-11`
- Base branch: `main`
- Round kickoff branch: `codex/r07-round-kickoff`

## Scope

Execute R07 as a parallel implementation round to move from scaffolded conversion outputs to a browsable and repeatable end-to-end migration flow for real XML screens.

## Lanes

| Lane | Branch | Worktree | Focus |
|---|---|---|---|
| `ui-widget-materialization` | `codex/r07-ui-widget-materialization` | `/tmp/miflatform-r07-ui-widget-materialization` | Upgrade UI codegen from generic node boxes to deterministic React+MUI widget mapping for core tags |
| `behavior-store-scaffold` | `codex/r07-behavior-store-scaffold` | `/tmp/miflatform-r07-behavior-store-scaffold` | Generate Zustand store/action scaffolds from events/bindings/transactions for generated screens |
| `pipeline-e2e-automation` | `codex/r07-pipeline-e2e-automation` | `/tmp/miflatform-r07-pipeline-e2e-automation` | Add one-command migration pipeline and end-to-end report/preview synchronization workflow |

## Global Gates

- `python3 -m unittest discover -s tests -p 'test_*.py' -v`
- `cd preview-host && npm run build`
- User-facing flow changes must update `/Users/biblepark/Desktop/works/miflatform-migrator/USER_MANUAL.md` in the same round.
- All lane handoff files are completed.

## Dispatch Procedure

1. Generate subagent briefs:
2. `scripts/render_subagent_briefs.py --config ops/subagents/round_r07.json --out-dir out/subagent-briefs-r07`
3. Create lane worktrees:
4. `scripts/setup_round_parallel.sh r07 main ui-widget-materialization behavior-store-scaffold pipeline-e2e-automation`
5. Dispatch each brief in `out/subagent-briefs-r07/`.
6. Collect handoffs and merge by `/docs/multi-agent/PM_MERGE_CHECKLIST.md`.

## Notes

- R07 should preserve R06 commands (`gen-ui`, `sync-preview`) while adding a higher-level migration flow.
- Generated migration inputs/outputs remain non-versioned (`.gitignore` policy).
