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

Minimum entities:

- `Screen`: root metadata and bounds
- `Node`: UI component tree with layout/styling/binding metadata
- `Dataset`: schema (`colinfo`) and records (`record`) plus operations
- `Binding`: UI-to-dataset/property connections
- `Event`: user/system event declarations
- `ActionFlow`: normalized behavior chain from event handlers
- `Transaction`: API/data operation intent
- `ScriptBlock`: extracted script body with dependency mapping
- `SourceRef`: source XML path, node path, and line index

## 3) Validation Gates

Coverage gates:

- Unknown tag count must be `0`.
- Unknown attribute count must be `0`.
- Unmapped event count must be `0`.
- Unmapped transaction count must be `0`.
- Unmapped script block count must be `0`.

Roundtrip gate:

- `XML -> AST -> Canonical XML` structural diff must be `0` except approved normalizations.

Fidelity gates:

- Tree hash parity for component hierarchy.
- Layout signature parity for position/size/z-order.
- Binding signature parity for dataset-field mapping.

Traceability gate:

- 100% of generated UI/API artifacts include source references.

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

## 6) Initial Tooling Choices

- Python: parser/IR/validator/codegen orchestration
- Node: preview host and generated app/API runtime
- Testing:
- Python unit tests for parser and validator
- JavaScript tests for generated frontend/API contracts

## 7) Round 1 Implemented Contract

Python package:

- `src/migrator/models.py`: `SourceRef`, `AstNode`, `ScreenIR`, `ParseStats`, `ValidationGate`, `ParseReport`
- `src/migrator/parser.py`: strict parser bootstrap and unknown tag/attr gate evaluation
- `src/migrator/cli.py`: command-line interface

CLI contract:

- `mifl-migrator parse <xml_path> --out <report.json> [--strict] [--capture-text] [--known-tags-file <txt>] [--known-attrs-file <json>] [--pretty]`

Gate behavior in bootstrap:

- `unknown_tag_count`
- `unknown_attr_count`
- `--strict` returns non-zero exit code when any gate fails.

Known-profile inputs:

- Tag profile file: newline-delimited tag names
- Attribute profile file: JSON map like `{ "Screen": ["id"], "*": ["commonAttr"] }`
