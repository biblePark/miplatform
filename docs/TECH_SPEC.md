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

Current implemented entities (R05):

- `Screen`: root metadata and bounds
- `Node` (`AstNode`): raw UI component tree
- `Dataset`: schema (`column`) and records (`record`)
- `Binding`: `bind*` attributes captured from nodes
- `Event`: `on*` attributes and `Event` nodes
- `Transaction`: transaction/service request nodes
- `ScriptBlock`: script/function-like nodes and bodies
- `SourceRef`: source XML path, node path, and line index

## 3) Validation Gates

Current implemented gates (R05):

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

Preview host scaffold (R05, repository-level runtime shell):

- `/preview-host/src/main.tsx`
- `/preview-host/src/app/PreviewApp.tsx`
- `/preview-host/src/routes/PreviewScreenRoute.tsx`
- `/preview-host/src/manifest/screens.manifest.schema.json`
- `/preview-host/src/manifest/screens.manifest.json`
- `/preview-host/src/screens/registry.ts`

## 5) Preview Strategy

- Keep a thin host app with a fixed entry point (`main.tsx` + `PreviewApp.tsx`).
- Load generated screens through manifest-driven routes:
- `/preview/:screenId`
- This solves "single component without app entry" by always rendering inside the host shell.

Screens manifest contract (R05):

- `schemaVersion`: currently fixed to `"1.0"`
- `generatedAtUtc`: ISO-8601 datetime string (UTC expected)
- `screens[]` item fields:
- `screenId`: route key used by `/preview/:screenId`
- `entryModule`: loader key (for example `screens/placeholder/PlaceholderScreen`)
- `sourceXmlPath`: source trace path for diagnostics
- `sourceNodePath`: source node path for diagnostics
- `title` (optional): preview title override

Loader contract (R05):

- Route handler resolves `screenId` from URL.
- Host finds the matching manifest entry by `screenId`.
- Host resolves a module loader by `entryModule` in `src/screens/registry.ts`.
- Loaded module must default-export a React component that receives `{ manifestEntry }`.
- Missing `screenId` or missing loader must produce explicit contract errors in host UI (no silent fallback).

## 6) Tooling Choices

- Python: parser/IR/validator/codegen orchestration
- Node: preview host and generated app/API runtime
- Testing:
- Python unit tests for parser/validator/CLI
- JavaScript tests for generated frontend/API contracts

## 7) Implemented Contract (R01-R05)

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
- `map-api` command for TransactionIR-to-Express scaffold and mapping report
- `src/migrator/api_mapping.py`:
- transaction mapping planner (`success`/`failure`/`unsupported`)
- route/service scaffold renderer for Express JavaScript output
- mapping report model with summary counters and per-transaction status

CLI contract:

- `mifl-migrator parse <xml_path> --out <report.json> [--strict] [--capture-text] [--known-tags-file <txt>] [--known-attrs-file <json>] [--disable-roundtrip-gate] [--roundtrip-mismatch-limit <n>] [--pretty]`
- `mifl-migrator batch-parse <input_dir> --out-dir <dir> --summary-out <summary.json> [--recursive] [single-parse options...]`
- `mifl-migrator map-api <xml_path> --out-dir <generated_api_dir> --report-out <mapping_report.json> [single-parse options...]`
- `mifl-migrator gen-ui <xml_path> --out-dir <generated_ui_dir> --report-out <ui_report.json> [single-parse options...] [--render-policy-mode <strict|mui|auto>] [--auto-risk-threshold <0.0-1.0>]`
- `mifl-migrator migrate-e2e <xml_path> [single-parse options...] [--render-policy-mode <strict|mui|auto>] [--auto-risk-threshold <0.0-1.0>]`

Known-profile inputs:

- Tag profile file: newline-delimited tag names
- Attribute profile file: JSON map like `{ "Screen": ["id"], "*": ["commonAttr"] }`

## 8) API Mapping Contract (R06)

Scope:

- Input is `ScreenIR.transactions` (`list[TransactionIR]`) extracted by parser stage.
- Output is Express scaffold files and a machine-readable JSON mapping report.
- Existing parse/validation gate semantics are unchanged.

Input contract:

- Each `TransactionIR` contributes:
- `transaction_id` (preferred symbolic identifier)
- `endpoint` (target route path)
- `method` (HTTP verb)
- `source` (traceability path/line)
- `node_tag` (used for ScriptTransactionCall-specific normalization)

Endpoint normalization rules:

- General normalization:
- trim whitespace
- convert `\` to `/`
- strip query/fragment suffixes for route matching
- force leading `/`, collapse repeated `/`, trim trailing `/` except root
- `ScriptTransactionCall` additional normalization:
- `service::path` style endpoints become `/service/path`
- absolute URLs are converted to their URL path (for example `http://host/a/b` -> `/a/b`)

Mapping decision contract:

- `success`:
- endpoint and method exist
- method is one of `GET|POST|PUT|PATCH|DELETE`
- route key `(method, normalized_endpoint)` is unique within the screen
- service function naming is collision-safe and deterministic:
- default transaction nodes use `transaction_id|node_id|transaction_<index>`
- `ScriptTransactionCall` uses `transaction_id + method + normalized_endpoint` seed before JS identifier normalization
- remaining collisions add numeric suffixes (`<name>2`, `<name>3`, ...)
- `failure`:
- missing required fields (`missing_endpoint`, `missing_method`)
- duplicate route conflict (`duplicate_route:<METHOD>:<PATH>`) where `<PATH>` is normalized
- duplicates follow deterministic policy `route_key(method, normalized_endpoint):first_seen_wins`
- duplicate result entries include `duplicate_of_index` and `duplicate_of_transaction_id`
- `unsupported`:
- method present but unsupported (`unsupported_http_method:<METHOD>`)

Output contract:

- Route stub: `<out-dir>/src/routes/<screen-stem>.routes.js`
- Service stub: `<out-dir>/src/services/<screen-stem>.service.js`
- Mapping report JSON (`--report-out`) includes:
- `summary.total_transactions`
- `summary.mapped_success`
- `summary.mapped_failure`
- `summary.unsupported`
- `duplicate_policy`
- `results[]` with per-transaction status/reason, generated route/service identifiers, and duplicate linkage metadata (`duplicate_of_index`, `duplicate_of_transaction_id`)

Exception and exit contract:

- XML parse/file errors follow existing CLI behavior (`ParseStrictError`/`FileNotFoundError` -> exit code `2`).
- `map-api` returns exit code `2` when `mapped_failure > 0`, otherwise `0`.
- `unsupported` mappings are reported but do not force non-zero exit by themselves.

## 9) Multi-Agent Operational Contract (R04)

Parallel round support artifacts:

- Templates: `/docs/multi-agent/`
- Example lane config: `/ops/subagents/example_round_r04.json`
- Worktree setup script: `/scripts/setup_round_parallel.sh`
- Brief rendering script: `/scripts/render_subagent_briefs.py`

Expected PM flow:

1. Define lane config JSON.
2. Generate lane briefs.
3. Create lane worktrees.
4. Dispatch briefs and collect handoffs.
5. Merge by checklist and rerun full gates.

## 10) Preview Host Contract Validation (R05)

Python-side contract validator (for testable schema integrity):

- `src/migrator/preview_manifest.py` validates `screens manifest` payloads.
- Validation covers:
- required fields
- screen id uniqueness
- `schemaVersion` fixed value check
- `entryModule` naming contract (`screens/...`)
- timestamp format sanity check
- `tests/test_preview_manifest.py` provides contract regression coverage.

## 11) Batch Summary Aggregation Contract (R05)

`batch-parse` summary now includes aggregation fields for round-level monitoring:

- `gate_pass_fail_counts`: per gate `{ pass_count, fail_count }`
- `failure_reason_counts`: grouped failure reasons (`strict_gate_failure`, `xml_parse_failure`, ...)
- `failure_file_counts`: failure count by file path
- `failure_file_leaderboard`: ranked list with:
- `file`
- `failed_gate_count`
- `failed_gates`
- `failure_reasons`

Aggregation behavior:

- On strict gate failures, the file is re-parsed in non-strict mode for gate accounting.
- Parse-level failures still appear in `failures[]` and `failure_reason_counts`.
- Summary remains backward-compatible for existing base fields:
- `generated_at_utc`, `input_dir`, `out_dir`, `total_xml_files`, `reports_written`, `failures`.

## 12) Runtime Behavior Wiring Contract (R08-R09)

Scope:

- Generated UI screen modules and generated behavior store/actions must share deterministic file/import/hook naming.
- Contract is computed from `screen_id` through `src/migrator/runtime_wiring.py` and reused by both codegen lanes.

Deterministic naming contract:

- Screen file stem: `to_file_stem(screen_id)`
- Screen component name: `to_component_name(screen_id)`
- Behavior store file: `<stem>.store.ts`
- Behavior actions file: `<stem>.actions.ts`
- UI -> store import: `../behavior/<stem>.store`
- Store hook name: `use<PascalScreenId>BehaviorStore`
- Store -> actions import: `./<stem>.actions`

Event/action runtime contract:

- Action names still follow duplicate-safe policy:
- base action: event/transaction seed -> PascalCase
- collisions: first keeps base name, later entries append numeric suffix (`<name>2`, `<name>3`, ...)
- `gen-behavior-store` now emits event-to-action bindings:
- `screenBehaviorEventActionBindings[]` in actions module
- `event_action_bindings[]` in behavior report JSON
- `gen-ui` uses the same planned bindings and wires supported XML `on*` events to React handler props on generated widget shells.
- Supported event mapping policy is expanded beyond minimal click/input events to broader React DOM events (mouse, keyboard, focus, form, drag/drop, pointer, touch, media, animation, transition, wheel).
- Unsupported event risks are preserved in structured report fields:
- `summary.total_event_attributes`
- `summary.runtime_wired_event_props`
- `summary.unsupported_event_bindings`
- Render policy decision evidence is preserved in structured report fields:
- `requested_mode`, `mode`, `decision_reason`, `risk_score`
- `auto_risk_threshold`: effective threshold used by policy evaluator
- `risk_signal_counts`: `total_nodes`, `positioned_nodes`, `fallback_nodes`, `tab_nodes`, `event_attributes`
- `risk_signal_scores`: weighted per-signal contributions (`positioned_nodes`, `fallback_nodes`, `event_attributes`, `tab_nodes`) and `total`
- `unsupported_event_inventory[]` entries with deterministic order and fields:
- `node_path`, `node_tag`, `event_name`, `source_attr_name`, `handler`, `action_name`, `reason`, `warning`, `source`
- `reason` values:
- `missing_behavior_action_binding`
- `missing_react_event_mapping`
- `auto` mode threshold source priority:
- CLI option `--auto-risk-threshold` (or function argument in library usage)
- environment variable `MIFL_UI_AUTO_RISK_THRESHOLD`
- built-in default `0.58`

Generation behavior update:

- `gen-ui` now also emits deterministic behavior scaffolds under `src/behavior/` so generated screen imports are immediately resolvable.
- `migrate-e2e` `gen_ui` stage metadata includes behavior file references and event wiring counters (`wired_event_bindings`, `total_event_attributes`, `runtime_wired_event_props`, `unsupported_event_bindings`) plus render policy evidence (`requested_mode`, `mode`, `decision_reason`, `risk_score`, `auto_risk_threshold`, `risk_signal_counts`, `risk_signal_scores`).
- Widget materialization baseline now includes legacy aliases:
- container-like tags: `window`, `form`, `div`, `shape`, `tab`, `tabpage`
- widget-like tags: `textarea`, `maskedit`, `image`, `radio`, `checkbox`, `calendar`, `spin`, `treeview`, `webbrowser`, `msie`, `rexpert`
- non-visual meta tags (`dataset`, `colinfo`, `cell`, `script`, etc.) are emitted as traceable shell nodes without unsupported-widget warnings.

## 13) Report Query/Display Contract (R11)

Scope:

- `scripts/report_view.py` provides a single query UX for major report artifacts:
- `*.migration-summary.json` (`migration_summary`)
- `regression-summary.json` (`regression_summary`)
- `prototype-acceptance.json` (`prototype_acceptance`)

Input contract:

- Accepts one or more file paths and/or directory paths.
- Directory paths are scanned recursively for `*.json`.
- Report type can be forced via `--report-type` or auto-detected via payload shape (`--report-type auto`, default).

Auto-detection rules:

- `prototype_acceptance`: payload contains `verdict` (string) and `kpi_results` (list)
- `regression_summary`: payload contains `risk_trends` (object) and `stage_status_counts` (object)
- `migration_summary`: payload contains `stages` (object)

Output contract (`--format json`):

- Root fields:
- `schema_version` (`1`)
- `report_count`
- `reports[]`
- `reports[]` fields:
- `schema_version` (`1`)
- `source_file` (absolute path)
- `report_type` (`migration_summary|regression_summary|prototype_acceptance`)
- `generated_at_utc` (nullable string)
- `summary` (normalized per-type key metrics)

Per-type normalized summary fields:

- `migration_summary`:
- `screen_id`, `overall_status`, `overall_exit_code`
- `stage_statuses`
- `warning_count`, `error_count`
- `fidelity_risk_detected`, `missing_node_count`, `position_style_nodes_with_risk`
- `unsupported_event_bindings`, `event_runtime_wiring_coverage_ratio`
- `regression_summary`:
- `overall_status`, `overall_exit_code`
- `total_samples`, `success_count`, `failure_count`
- `stage_failure_counts`
- `malformed_xml_blocker_count`
- `risk_trends.extraction|mapping|fidelity` rollup fields
- `prototype_acceptance`:
- `verdict`
- `total_migration_summaries`, `failed_migration_count`, `fidelity_risk_count`
- `unsupported_event_bindings`, `unresolved_transaction_adapter_signals`
- `event_runtime_wiring_coverage_ratio`
- `total_kpi_count`, `passed_kpi_count`, `failed_kpi_count`, `failed_kpi_names`

Text output contract (`--format text`, default):

- One report block per artifact.
- Each block starts with `[<report_type>] <source_file>`.
- Followed by deterministic key metric lines for terminal scanability.

Failure/exit contract:

- Returns `0` on success.
- Returns `2` when:
- input path is missing
- explicit file input is not a supported report contract
- JSON parsing fails or required report fields are malformed
- no supported reports are found
- For directory inputs in auto mode, unsupported JSON payloads are skipped and counted on stderr.

Regression coverage:

- `tests/test_report_view.py` validates:
- `migrate-e2e` + `prototype-accept` output query path
- `run_real_sample_e2e_regression.py` output query path
- unsupported explicit file failure gate
