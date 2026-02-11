# R09 Kickoff

## Round Metadata

- Round ID: `R09`
- Date: `2026-02-11`
- Base branch: `main`
- Round kickoff branch: `codex/r09-round-kickoff`

## Scope

Execute R09 as a parallel implementation round to harden proof-oriented migration quality gates for UI fidelity and behavior completeness.

## Lanes

| Lane | Branch | Worktree | Focus |
|---|---|---|---|
| `fidelity-audit-gates` | `codex/r09-fidelity-audit-gates` | `/tmp/miflatform-r09-fidelity-audit-gates` | Add deterministic XML-to-generated-UI completeness audit gates and report schema |
| `event-wiring-coverage` | `codex/r09-event-wiring-coverage` | `/tmp/miflatform-r09-event-wiring-coverage` | Expand generated UI event binding coverage and unsupported-event risk reporting |
| `transaction-adapter-contract` | `codex/r09-transaction-adapter-contract` | `/tmp/miflatform-r09-transaction-adapter-contract` | Replace transaction TODO actions with generated API adapter contracts for runtime behavior scaffolds |

## Global Gates

- `python3 -m unittest discover -s tests -p 'test_*.py' -v`
- `cd preview-host && npm run build`
- For user-visible command/flow changes, update `/Users/biblepark/Desktop/works/miflatform-migrator/USER_MANUAL.md` in the same round.
- All lane handoff files are completed.

## Dispatch Procedure

1. Generate subagent briefs:
2. `scripts/render_subagent_briefs.py --config ops/subagents/round_r09.json --out-dir out/subagent-briefs-r09`
3. Create lane worktrees:
4. `scripts/setup_round_parallel.sh r09 main fidelity-audit-gates event-wiring-coverage transaction-adapter-contract`
5. Dispatch each brief in `out/subagent-briefs-r09/`.
6. Collect handoffs and merge by `/docs/multi-agent/PM_MERGE_CHECKLIST.md`.

## Notes

- R09 focuses on measurable verification signals to answer completeness questions without relying on native MIPLATFORM runtime.
- Generated migration inputs/outputs remain non-versioned (`.gitignore` policy).
