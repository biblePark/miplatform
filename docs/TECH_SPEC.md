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

Current implemented gates (R02):

- `unknown_tag_count` (`expected=0`)
- `unknown_attr_count` (`expected=0`)
- `roundtrip_structural_diff` (`expected=0`)
- `dataset_extraction_coverage` (`value == expected`)
- `binding_extraction_coverage` (`value == expected`)
- `event_extraction_coverage` (`value == expected`)

Planned additional gates:

- transaction mapping coverage
- script block mapping coverage
- layout signature parity

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

## 7) Implemented Contract (R01-R02)

Python package:

- `src/migrator/models.py`:
- `SourceRef`, `AstNode`, `ScreenIR`, `ParseStats`, `ValidationGate`, `ParseReport`
- `DatasetIR`, `DatasetColumnIR`, `DatasetRecordIR`, `BindingIR`, `EventIR`
- `src/migrator/parser.py`:
- strict parser bootstrap
- unknown tag/attr checks
- IR extraction for dataset/binding/event
- strict gate evaluation
- `src/migrator/validator.py`:
- structural roundtrip diff between source XML tree and AST
- `src/migrator/cli.py`:
- `parse` command with report output

CLI contract:

- `mifl-migrator parse <xml_path> --out <report.json> [--strict] [--capture-text] [--known-tags-file <txt>] [--known-attrs-file <json>] [--disable-roundtrip-gate] [--pretty]`

Known-profile inputs:

- Tag profile file: newline-delimited tag names
- Attribute profile file: JSON map like `{ "Screen": ["id"], "*": ["commonAttr"] }`
