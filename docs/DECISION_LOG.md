# Decision Log (ADR Style)

## ADR-0001: Validation-First Migration Strategy

- Date: `2026-02-11`
- Status: Accepted

Context:

- Original MIPLATFORM runtime may be unavailable for direct visual comparison.
- XML complexity is high and omission risk is critical.

Decision:

- Use validation-first design:
- strict parser
- canonical IR
- roundtrip checks
- coverage gates
- full source traceability

Consequences:

- Higher initial engineering effort.
- Stronger confidence and auditability for enterprise migration.

## ADR-0002: Round-Based Multi-Threaded Worktree Workflow

- Date: `2026-02-11`
- Status: Accepted

Context:

- Multiple threads/agents must work concurrently without stepping on each other.

Decision:

- Use one branch + one worktree per round.
- Enforce naming pattern `codex/r<round>-<scope>`.
- Merge only after round gates pass.

Consequences:

- Better isolation and rollback safety.
- Requires disciplined history/document updates each round.

