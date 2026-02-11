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

## ADR-0004: Structural Roundtrip Diff as First Completeness Proof

- Date: `2026-02-11`
- Status: Accepted

Context:

- Runtime visual comparison may not be available during migration.
- A direct structural completeness proof is needed before code generation.

Decision:

- Introduce roundtrip structural diff between source XML tree and parsed AST.
- Add extraction coverage gates for `Dataset`, binding attributes (`bind*`), and event points (`on*` and `Event` nodes).

Consequences:

- Parser regressions can be detected early with deterministic gates.
- Semantic behavior equivalence is still pending and requires later transaction/script mapping rounds.

## ADR-0005: Canonical Hash Validation and Detailed Mismatch Reporting

- Date: `2026-02-11`
- Status: Accepted

Context:

- Structural diff count alone is not enough for diagnosis at ERP scale.

Decision:

- Add path-level mismatch records (`position_path`, reason, source/AST signatures).
- Add deterministic canonical XML generation for source XML and AST regeneration.
- Add canonical hash match gate.

Consequences:

- Completeness failures are diagnosable without runtime rendering.
- Reports become large on highly divergent files; mismatch list is capped by config.

## ADR-0006: Batch Parse as First-Class CLI Capability

- Date: `2026-02-11`
- Status: Accepted

Context:

- Migration work must run against large XML sets, not only single-screen files.

Decision:

- Add `batch-parse` command with per-file report output and summary JSON.
- Continue processing all files in a batch and return non-zero when failures exist.

Consequences:

- Enables round-level execution and coverage tracking for large repositories.
- Requires follow-up rounds for richer aggregated metrics and pipeline integration.

## ADR-0007: Standardized Subagent Templates and Lane Orchestration

- Date: `2026-02-11`
- Status: Accepted

Context:

- Parallel rounds require consistent assignments, handoffs, and merge criteria.
- Ad-hoc instructions increase omission and integration risk.

Decision:

- Add canonical subagent templates under `/docs/multi-agent/`.
- Add round config example under `/ops/subagents/`.
- Add automation scripts for lane setup and brief generation under `/scripts/`.

Consequences:

- PM can dispatch parallel lanes faster with consistent quality.
- Requires round config maintenance to keep templates aligned with real scope.

## ADR-0008: Scaffold-First Delivery for API and Preview Outputs

- Date: `2026-02-11`
- Status: Accepted

Context:

- Migration pipeline needed executable artifacts quickly, but full semantic conversion is still pending.

Decision:

- Deliver scaffold-first outputs in R05:
- `map-api` command generates Express route/service stubs from `TransactionIR`.
- `preview-host/` provides manifest-driven React route shell with placeholder screen modules.

Consequences:

- Teams can validate integration flow early with deterministic outputs.
- Generated business logic remains placeholder-level and requires later semantic mapping rounds.

## ADR-0009: Aggregated Batch Summary for Operational Visibility

- Date: `2026-02-11`
- Status: Accepted

Context:

- Single-file parse reports are insufficient for monitoring large migration batches.

Decision:

- Extend `batch-parse` summary with gate pass/fail counts, failure reason counts, and per-file leaderboard.

Consequences:

- PM can prioritize high-impact failures faster during large runs.
- Strict-failure fallback re-parse introduces additional cost on failing files.
