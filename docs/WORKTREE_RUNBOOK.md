# Worktree Runbook (Multi-Threaded Rounds)

## Objective

Enable safe parallel execution across rounds while preserving reproducibility and merge quality.

## Round Model

- One round = one scoped objective.
- One round = one branch for single-thread rounds, or multiple lane branches for parallel rounds.
- One lane = one dedicated worktree directory.

## Branch and Worktree Naming

- Branch prefix: `codex/`
- Branch pattern: `codex/r<round-number>-<scope>`
- Worktree pattern: `/tmp/miflatform-r<round-number>-<scope>`

Examples:

- Branch: `codex/r04-api-mapping`
- Worktree: `/tmp/miflatform-r04-api-mapping`

## Standard Flow (Single Lane)

1. Select base branch (usually `main`).
2. Create worktree and branch.
3. Implement scoped changes only in that worktree.
4. Run required checks for the round.
5. Commit with round-aware message.
6. Merge branch back to base after review/gate pass.
7. Remove worktree.

## Parallel Lane Flow (Multi-Agent)

1. Define lanes and gate ownership.
2. Generate lane briefs from config:
3. `scripts/render_subagent_briefs.py --config ops/subagents/<round>.json --out-dir out/subagent-briefs-<round>`
4. Create lane worktrees:
5. `scripts/setup_round_parallel.sh r<round> main <lane-a> <lane-b> ...`
6. Dispatch each generated brief to corresponding subagent.
7. Collect handoffs from each lane.
8. Merge lanes in conflict-minimizing order.
9. Run full tests after each merge group.

## Merge Rules

- No merge if validation gates fail.
- No merge if docs are stale against implementation.
- No merge with unresolved generated/manual ownership conflicts.
- For parallel rounds, no final merge without all required lane handoffs.

## Round Checklist

- Scope defined in one sentence.
- Validation gates listed and executed.
- Decision log updated when rules/specs changed.
- Round history updated.
- Multi-agent rounds only:
- lane briefs generated and archived
- lane handoff docs collected

