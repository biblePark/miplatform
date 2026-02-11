# Subagent Task Template

Fill and send this file to each subagent before work starts.

## Assignment

- Round: `{{ROUND_ID}}`
- Lane: `{{LANE_NAME}}`
- Branch: `{{BRANCH_NAME}}`
- Worktree: `{{WORKTREE_PATH}}`
- Base branch: `{{BASE_BRANCH}}`

## Objective

{{LANE_OBJECTIVE}}

## Required Deliverables

{{DELIVERABLES_LIST}}

## Constraints

- Do not edit files outside assigned scope unless explicitly required.
- Do not bypass or mute validation gates.
- Do not merge to `main` directly.
- Keep commits focused and reproducible.

## Required Checks

{{REQUIRED_CHECKS_LIST}}

## Handoff Requirements

- Produce completed handoff doc using:
- `/docs/multi-agent/SUBAGENT_HANDOFF_TEMPLATE.md`
- Include:
- changed file list
- test/command results
- unresolved risks/questions

