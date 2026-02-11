# Project Rules

## 1) Migration Integrity Is Mandatory

- No silent fallback and no silent drop of XML nodes, attributes, datasets, events, or scripts.
- Unsupported constructs must fail with explicit diagnostics.
- Every source node must remain traceable in transformed artifacts.

## 2) Validation Is a Release Gate

- Conversion is not "done" unless validation gates pass.
- Mandatory gates:
- `unknown_tag_count == 0`
- `unknown_attr_count == 0`
- `roundtrip_structural_diff == 0` for canonicalized XML
- `event_mapping_coverage == 100%`
- `transaction_mapping_coverage == 100%`

## 3) Source of Truth

- `docs/` defines process and standards.
- Generated files must include metadata mapping to source XML path and line.
- Manual edits on generated files are prohibited unless promoted to templates/generators.

## 4) Fail Fast

- Ambiguous parsing or mapping must stop the pipeline.
- Warnings are allowed only for approved non-functional differences and must be documented.

## 5) Round-Based Delivery

- Work happens by rounds.
- One round equals one branch and one dedicated worktree.
- Merge only after gates pass and history is updated.

## 6) Branch Naming Convention

- Prefix is always `codex/`.
- Pattern: `codex/r<round-number>-<short-scope>`
- Examples:
- `codex/r01-parser-bootstrap`
- `codex/r02-ir-schema`

## 7) Documentation Discipline

- Any rule change updates:
- `/docs/PROJECT_RULES.md`
- `/docs/DECISION_LOG.md`
- `/docs/ROUND_HISTORY.md`

