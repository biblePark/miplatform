# Worktree Runbook (Multi-Threaded Rounds)

## Objective

Enable safe parallel execution across rounds while preserving reproducibility and merge quality.

## Round Model

- One round = one scoped objective.
- One round = one branch.
- One round = one dedicated worktree directory.

## Branch and Worktree Naming

- Branch prefix: `codex/`
- Branch pattern: `codex/r<round-number>-<scope>`
- Worktree pattern: `../miflatform-r<round-number>-<scope>`

Examples:

- Branch: `codex/r01-parser-bootstrap`
- Worktree: `../miflatform-r01-parser-bootstrap`

## Standard Flow

1. Select base branch (usually `main`).
2. Create worktree and branch:
3. `git worktree add ../miflatform-r01-parser-bootstrap -b codex/r01-parser-bootstrap <base-branch>`
4. Implement scoped changes only in that worktree.
5. Run required checks for the round.
6. Commit with round-aware message.
7. Merge branch back to base after review/gate pass.
8. Remove worktree:
9. `git worktree remove ../miflatform-r01-parser-bootstrap`

## Merge Rules

- No merge if validation gates fail.
- No merge if docs are stale against implementation.
- No merge with unresolved generated/manual ownership conflicts.

## Round Checklist

- Scope defined in one sentence.
- Validation gates listed and executed.
- Decision log updated when rules/specs changed.
- Round history updated.

