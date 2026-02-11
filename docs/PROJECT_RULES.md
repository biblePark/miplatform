# Project Rules

## 1) Migration Integrity Is Mandatory

- No silent fallback and no silent drop of XML nodes, attributes, datasets, events, scripts, or transactions.
- Unsupported constructs must fail with explicit diagnostics.
- Every source node must remain traceable in transformed artifacts.

## 2) Validation Is a Release Gate

- Conversion is not done unless validation gates pass.
- Mandatory gates include:
- `unknown_tag_count == 0`
- `unknown_attr_count == 0`
- `roundtrip_structural_diff == 0`
- `canonical_roundtrip_hash_match == true`
- extraction coverage gates for dataset/binding/event/transaction/script

## 3) Source of Truth

- `docs/` defines process and standards.
- Generated files must include metadata mapping to source XML path and line.
- Manual edits on generated files are prohibited unless promoted to templates/generators.

## 4) Fail Fast

- Ambiguous parsing or mapping must stop the pipeline.
- Warnings are allowed only for approved non-functional differences and must be documented.

## 5) Round-Based Delivery

- Work happens by rounds.
- One round can include multiple parallel lanes.
- Merge only after gates pass and history is updated.

## 6) Branch Naming Convention

- Prefix is always `codex/`.
- Pattern: `codex/r<round-number>-<short-scope>`.
- Examples:
- `codex/r01-parser-bootstrap`
- `codex/r04-api-mapping`

## 7) Multi-Agent Governance

- Every lane must have a written assignment template.
- Every lane must return a handoff document before integration.
- PM must use merge checklist before final merge.
- Canonical templates live under `/docs/multi-agent/`.

## 8) Documentation Discipline

- Any rule change updates:
- `/docs/PROJECT_RULES.md`
- `/docs/DECISION_LOG.md`
- `/docs/ROUND_HISTORY.md`
- Any user-facing flow change updates:
- `/Users/biblepark/Desktop/works/miflatform-migrator/USER_MANUAL.md`
- For every round merge, if CLI commands/input paths/output locations/preview verification steps changed, the merge is incomplete until `USER_MANUAL.md` is updated in the same round.
