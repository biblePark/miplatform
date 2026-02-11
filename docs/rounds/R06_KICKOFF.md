# R06 Kickoff

## Round Metadata

- Round ID: `R06`
- Date: `2026-02-11`
- Base branch: `main`
- Round kickoff branch: `codex/r06-round-kickoff`

## Scope

Execute R06 as a parallel implementation round for first-pass code generation that can be opened and checked in browser with traceability to XML source.

## Lanes

| Lane | Branch | Worktree | Focus |
|---|---|---|---|
| `ui-codegen-core` | `codex/r06-ui-codegen-core` | `/tmp/miflatform-r06-ui-codegen-core` | Parse report/screen IR -> React TSX component generation scaffold (layout + control placeholders) |
| `preview-manifest-sync` | `codex/r06-preview-manifest-sync` | `/tmp/miflatform-r06-preview-manifest-sync` | Generate/update preview manifest + registry wiring for generated screens |
| `api-script-tx-sync` | `codex/r06-api-script-tx-sync` | `/tmp/miflatform-r06-api-script-tx-sync` | Ensure ScriptTransactionCall flows into Express mapping artifacts with deterministic naming policy |

## Global Gates

- `python3 -m unittest discover -s tests -p 'test_*.py' -v`
- `cd preview-host && npm run build`
- Strict parse/canonical gates remain green on agreed validation sample set.
- All lane handoff files are completed.

## Dispatch Procedure

1. Generate subagent briefs:
2. `scripts/render_subagent_briefs.py --config ops/subagents/round_r06.json --out-dir out/subagent-briefs-r06`
3. Create lane worktrees:
4. `scripts/setup_round_parallel.sh r06 main ui-codegen-core preview-manifest-sync api-script-tx-sync`
5. Dispatch each brief in `out/subagent-briefs-r06/`.
6. Collect handoffs and merge by `/docs/multi-agent/PM_MERGE_CHECKLIST.md`.

## Notes

- `preview-host` build is currently green on `main` and must stay green in all lanes.
- Generated migration inputs/outputs remain non-versioned (`.gitignore` policy).
