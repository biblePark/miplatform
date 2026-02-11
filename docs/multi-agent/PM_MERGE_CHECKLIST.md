# PM Merge Checklist

Use this checklist when integrating multiple lane branches into `main`.

## Pre-Merge

- [ ] Every lane has a completed handoff document.
- [ ] Every lane branch is rebased or merge-ready against `main`.
- [ ] Validation commands are documented and reproducible.

## Integration

- [ ] Merge lowest-conflict lane first.
- [ ] Re-run full test suite after each merge group.
- [ ] Resolve conflicts by preserving validation/reporting behavior first.

## Post-Merge

- [ ] `docs/ROUND_HISTORY.md` updated.
- [ ] `docs/DECISION_LOG.md` updated for rule/architecture changes.
- [ ] Round summary shared with gate outcomes and residual risks.

