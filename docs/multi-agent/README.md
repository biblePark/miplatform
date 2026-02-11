# Multi-Agent Pack

This folder contains templates for parallel lane execution and merge orchestration.

## Files

- `ROUND_KICKOFF_TEMPLATE.md`: PM kickoff for one round.
- `SUBAGENT_TASK_TEMPLATE.md`: per-lane assignment template.
- `SUBAGENT_HANDOFF_TEMPLATE.md`: per-lane completion report template.
- `PM_MERGE_CHECKLIST.md`: merge safety checklist.

## Suggested Workflow

1. Prepare round config JSON under `ops/subagents/`.
2. Generate lane briefs with `scripts/render_subagent_briefs.py`.
3. Create worktrees with `scripts/setup_round_parallel.sh`.
4. Dispatch briefs to subagents.
5. Collect handoff docs and merge using checklist.

