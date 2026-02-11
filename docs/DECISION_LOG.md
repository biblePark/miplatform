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

## ADR-0003: Python Standard Library First for Parser Bootstrap

- Date: `2026-02-11`
- Status: Accepted

Context:

- Round 1 goal is to establish a deterministic parser/IR/CLI baseline quickly.
- External dependency adoption can slow bootstrap and increase setup variance.

Decision:

- Build parser bootstrap on `xml.etree.ElementTree` first.
- Keep parser interfaces and models ready to swap parser backend (for example to `lxml`) in later rounds.

Consequences:

- Faster bootstrap and simpler local execution.
- Source line fidelity may be limited in bootstrap mode and should be improved in subsequent rounds.
