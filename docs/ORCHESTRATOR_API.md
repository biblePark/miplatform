# Orchestrator API (Local)

This API wraps the existing `migrate-e2e` CLI pipeline as asynchronous local jobs.

## Scope

- Pipeline reuse: `parse -> map-api -> gen-ui -> fidelity-audit -> sync-preview -> preview-smoke`
- Job execution model: asynchronous background worker
- Job statuses: `queued`, `running`, `succeeded`, `failed`, `canceled`
- Error model: structured JSON errors (`error.code`, `error.message`, optional `error.details`)

## Run

```bash
PYTHONPATH=src python3 -m migrator.orchestrator_api \
  --host 127.0.0.1 \
  --port 8765 \
  --workspace-root . \
  --job-store-path ./out/orchestrator/jobs.json
```

Or via installed script:

```bash
mifl-migrator-api --host 127.0.0.1 --port 8765 --workspace-root .
```

## Endpoints

- `POST /jobs`
- `GET /jobs`
- `GET /jobs/{id}`
- `POST /jobs/{id}/cancel`
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
- `strict`, `capture_text`, `disable_roundtrip_gate`, `roundtrip_mismatch_limit`, `render_policy_mode`, `auto_risk_threshold`, `pretty`
- `known_tags_file`, `known_attrs_file`
- `summary_out`, `parse_report_out`, `map_report_out`, `ui_report_out`, `fidelity_report_out`, `preview_report_out`
- `manifest_file`, `registry_generated_file`

Default behavior:

- If output paths are omitted, per-job directories are created under `out/jobs/<job-id>/...`.
- If `preview_host_dir` is omitted, `use_isolated_preview_host=true` by default and preview-host is copied from `<workspace-root>/preview-host` into the job workspace.

### GET /jobs

Returns job history in reverse chronological order.

Query params:

- `limit` (optional, default `50`): positive integer
- `status` (optional): one or more statuses (`queued,running,succeeded,failed,canceled`)

Response shape:

```json
{
  "jobs": [
    {
      "id": "f4b0f4...",
      "status": "succeeded",
      "created_at_utc": "2026-02-19T01:02:03.000000+00:00"
    }
  ],
  "total": 1,
  "limit": 50,
  "status_filter": ["succeeded"]
}
```

### GET /jobs/{id}

Returns current job metadata and status.

### POST /jobs/{id}/cancel

Cancels a job and returns `202`.

- If job is `queued`, it transitions to `canceled` immediately.
- If job is `running`, cancellation is marked as requested and job transitions to `canceled` at the next safe point.
- If job is already terminal (`succeeded`, `failed`, `canceled`), current state is returned.

Response snippet:

```json
{
  "job": {
    "id": "f4b0f4...",
    "status": "canceled",
    "cancel_requested": true,
    "error": {
      "code": "job_canceled",
      "message": "Job canceled by request."
    }
  }
}
```

### GET /jobs/{id}/logs

Returns ordered structured log entries emitted by the orchestrator (`job_queued`, `job_started`, `pipeline_started`, `job_finished`, etc.).

### GET /jobs/{id}/artifacts

Returns parsed `migrate-e2e` summary artifacts once job is terminal.

- During `queued`/`running`, returns `409` with structured error.

## Job Store Persistence

- Job history is persisted to JSON (default: `<workspace-root>/out/orchestrator/jobs.json`).
- On server restart, previous jobs are loaded and available via `GET /jobs` and `GET /jobs/{id}`.
- Jobs that were non-terminal during restart are marked as failed with `error.code=job_incomplete_after_restart`.

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

List only succeeded jobs:

```bash
curl -sS "http://127.0.0.1:8765/jobs?status=succeeded&limit=20"
```

Cancel a job:

```bash
curl -sS -X POST "http://127.0.0.1:8765/jobs/<job-id>/cancel"
```
