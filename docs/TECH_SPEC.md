# Technical Specification (Baseline)

## 1) Architecture

Pipeline stages:

1. `ingest`: discover XML files and screen units
2. `parse`: convert XML into strict AST with source locations
3. `normalize`: map AST to canonical IR
4. `validate`: run coverage/roundtrip/fidelity checks
5. `codegen-front`: generate React/MUI/Zustand artifacts
6. `codegen-api`: generate Express route/service stubs
7. `report`: emit machine-readable and human-readable migration reports

## 2) Core IR Entities

Current implemented entities (R03):

- `Screen`: root metadata and bounds
- `Node` (`AstNode`): raw UI component tree
- `Dataset`: schema (`column`) and records (`record`)
- `Binding`: `bind*` attributes captured from nodes
- `Event`: `on*` attributes and `Event` nodes
- `Transaction`: transaction/service request nodes
- `ScriptBlock`: script/function-like nodes and bodies
- `SourceRef`: source XML path, node path, and line index

## 3) Validation Gates

Current implemented gates (R03):

- `unknown_tag_count` (`expected=0`)
- `unknown_attr_count` (`expected=0`)
- `roundtrip_structural_diff` (`expected=0`)
- `canonical_roundtrip_hash_match` (`expected=0` where mismatch is represented as 1)
- `dataset_extraction_coverage` (`value == expected`)
- `binding_extraction_coverage` (`value == expected`)
- `event_extraction_coverage` (`value == expected`)
- `transaction_extraction_coverage` (`value == expected`)
- `script_extraction_coverage` (`value == expected`)

Roundtrip details:

- Structural mismatches are stored in `ParseStats.roundtrip_mismatches` with position path and signatures.
- Canonical source/AST hashes are stored in `ParseStats.canonical_source_hash` and `ParseStats.canonical_ast_hash`.

Planned additional gates:

- transaction semantic mapping coverage (IR -> API contract)
- script semantic mapping coverage (IR -> executable handler mapping)
- layout signature parity for generated React output

## 4) Generated Output Shape

Planned structure:

- `/generated/frontend/src/screens/<ScreenId>.tsx`
- `/generated/frontend/src/stores/<screen-or-domain>.store.ts`
- `/generated/frontend/src/routes/generatedRoutes.tsx`
- `/generated/frontend/src/preview/PreviewApp.tsx`
- `/generated/frontend/src/manifest/screens.manifest.json`
- `/generated/api/src/routes/<domain>.routes.js`
- `/generated/api/src/services/<domain>.service.js`
- `/generated/reports/<round>/...`

## 5) Preview Strategy

- Keep a thin host app with a fixed entry point (`main.tsx` + `PreviewApp.tsx`).
- Load generated screens through manifest-driven routes:
- `/preview/:screenId`
- This solves "single component without app entry" by always rendering inside the host shell.

## 6) Tooling Choices

- Python: parser/IR/validator/codegen orchestration
- Node: preview host and generated app/API runtime
- Testing:
- Python unit tests for parser/validator/CLI
- JavaScript tests for generated frontend/API contracts

## 7) Implemented Contract (R01-R03)

Python package:

- `src/migrator/models.py`:
- parser report models
- extraction IR models (`Dataset`, `Binding`, `Event`, `Transaction`, `ScriptBlock`)
- mismatch and gate model types
- `src/migrator/parser.py`:
- strict parser
- unknown tag/attr checks
- IR extraction for dataset/binding/event/transaction/script
- strict gate evaluation
- `src/migrator/validator.py`:
- structural mismatch detector with path-level details
- canonical hash pair computation between source XML and AST regeneration
- `src/migrator/canonical.py`:
- deterministic canonical XML regeneration from XML trees and AST trees
- `src/migrator/cli.py`:
- `parse` command for single XML
- `batch-parse` command for directory-level migration reports

CLI contract:

- `mifl-migrator parse <xml_path> --out <report.json> [--strict] [--capture-text] [--known-tags-file <txt>] [--known-attrs-file <json>] [--disable-roundtrip-gate] [--roundtrip-mismatch-limit <n>] [--pretty]`
- `mifl-migrator batch-parse <input_dir> --out-dir <dir> --summary-out <summary.json> [--recursive] [single-parse options...]`

Known-profile inputs:

- Tag profile file: newline-delimited tag names
- Attribute profile file: JSON map like `{ "Screen": ["id"], "*": ["commonAttr"] }`
