# Orchestrator API (Local)

This API wraps the existing `migrate-e2e` CLI pipeline as asynchronous local jobs.

## Scope

- Pipeline reuse: `parse -> map-api -> gen-ui -> fidelity-audit -> sync-preview -> preview-smoke`
- Job execution model: asynchronous background worker
- Job statuses: `queued`, `running`, `succeeded`, `failed`, `canceled`
- Error model: structured JSON errors (`error.code`, `error.message`, optional `error.details`)

## Run

```bash
PYTHONPATH=src python3 -m migrator.orchestrator_api --host 127.0.0.1 --port 8765 --workspace-root .
```

Or via installed script:

```bash
mifl-migrator-api --host 127.0.0.1 --port 8765 --workspace-root .
```

## Endpoints

- `POST /jobs`
- `GET /jobs/{id}`
- `GET /jobs/{id}/logs`
- `GET /jobs/{id}/artifacts`
- `GET /health`

### POST /jobs

Creates an async migration job and returns `202`.

Required body fields:

- `xml_path`: source XML file path

Selected optional fields:

- `out_dir`, `api_out_dir`, `ui_out_dir`
- `preview_host_dir`, `preview_host_source_dir`, `use_isolated_preview_host`
- `strict`, `capture_text`, `disable_roundtrip_gate`, `roundtrip_mismatch_limit`, `pretty`
- `known_tags_file`, `known_attrs_file`
- `summary_out`, `parse_report_out`, `map_report_out`, `ui_report_out`, `fidelity_report_out`, `preview_report_out`
- `manifest_file`, `registry_generated_file`

Default behavior:

- If output paths are omitted, per-job directories are created under `out/jobs/<job-id>/...`.
- If `preview_host_dir` is omitted, `use_isolated_preview_host=true` by default and preview-host is copied from `<workspace-root>/preview-host` into the job workspace.

### GET /jobs/{id}

Returns current job metadata and status.

### GET /jobs/{id}/logs

Returns ordered structured log entries emitted by the orchestrator (`job_queued`, `job_started`, `pipeline_started`, `job_finished`, etc.).

### GET /jobs/{id}/artifacts

Returns parsed `migrate-e2e` summary artifacts once job is terminal.

- During `queued`/`running`, returns `409` with structured error.

## Structured Error Shape

```json
{
  "error": {
    "code": "validation_error",
    "message": "`xml_path` is required and must be a non-empty string.",
    "details": {
      "field": "xml_path"
    }
  }
}
```

## Minimal Example

```bash
curl -sS -X POST http://127.0.0.1:8765/jobs \
  -H 'content-type: application/json' \
  -d '{
    "xml_path": "tests/fixtures/simple_screen_fixture.txt",
    "strict": true,
    "capture_text": true,
    "known_tags_file": "tests/fixtures/known_tags_all.txt",
    "known_attrs_file": "tests/fixtures/known_attrs_all.json",
    "pretty": true
  }'
```

