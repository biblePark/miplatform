# Round Kickoff Template

Use this file as the PM kickoff message for one multi-threaded round.

## Round Metadata

- Round ID: `RXX`
- Date: `YYYY-MM-DD`
- Base branch: `main`
- Gate owner: `<name>`
- Merge owner: `<name>`

## Scope

- One-sentence round scope:
- Out of scope:

## Lanes

| Lane | Branch | Worktree | Owner | Goal |
|---|---|---|---|---|
| `lane-a` | `codex/rxx-lane-a` | `/tmp/miflatform-rxx-lane-a` | `<owner>` | `<goal>` |
| `lane-b` | `codex/rxx-lane-b` | `/tmp/miflatform-rxx-lane-b` | `<owner>` | `<goal>` |

## Global Gates (Must Pass Before Merge)

- Unit tests pass.
- Parser strict gates pass on agreed fixtures.
- No stale docs against implementation.
- Handoffs are complete for every lane.

## Delivery Contract

- Each lane delivers:
- PR-ready commit(s) on its own branch
- `/docs/multi-agent/SUBAGENT_HANDOFF_TEMPLATE.md` filled
- Commands executed and outputs summarized

