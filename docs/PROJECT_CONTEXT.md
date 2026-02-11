# Project Context

## Problem Summary

Legacy MIPLATFORM applications are saved as complex XML where UI, datasets, bindings, and behavior are mixed in nested structures.
Representative tags include `Dataset`, `Contents`, `colinfo`, `record`, plus proprietary component/event nodes.

Target migration split:

- Frontend: `Vite + React 19 + MUI v7 + Zustand`
- Backend API: `Express (JavaScript)`
- Migration engine: `Python`

## Hard Constraints

- Source applications are large ERP/order-management class systems.
- XML depth and breadth are high; omission risk is high.
- Runtime visual comparison against original platform may be unavailable.
- Exact functional behavior migration is required, not only static layout migration.

## Non-Negotiable Questions

1. Can we parse source XML accurately?
2. How do we prove completeness without original runtime rendering?
3. How do we prove behavior and business logic are migrated?

## Working Answers

1. Parse accuracy is addressed by strict parsing + canonical model + coverage gates.
2. Completeness is addressed by roundtrip checks, structural hash checks, and full traceability reports.
3. Behavior completeness is addressed by event/transaction/script mapping matrices with 100% coverage gates.

## Scope Boundaries

In scope:

- XML ingestion/parsing/normalization
- IR model definition and persistence
- Frontend/API code generation
- Validation/reporting toolchain
- Preview host for generated screens

Out of scope for initial rounds:

- Full semantic refactor of legacy logic
- Visual redesign of legacy UI
- Manual per-screen rewriting as default strategy

