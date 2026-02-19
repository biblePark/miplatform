# Desktop Preview Bridge (R13)

## Intent

- Primary operator UX is Python desktop (`PySide6`).
- Web preview remains a verification target for generated React output.
- Existing migrator core contracts (`migrate-e2e`, manifest, preview-smoke) stay unchanged.

## Runtime Module

- File: `/Users/biblepark/Desktop/works/miflatform-migrator/src/migrator/desktop_preview_bridge.py`
- Entry class: `DesktopPreviewBridge`

Core responsibilities:

1. Preview host lifecycle (`start_preview_host`, `stop_preview_host`, `preview_host_is_healthy`)
2. Run-output-aware preview host resolution:
- explicit run preview host directory, or
- `*.migration-summary.json` -> `stages.sync_preview.manifest_file` -> preview host root
3. Screen route open for selected `screenId` (`/preview/<screenId>`)
4. Embedded web view attempt (`PySide6.QtWebEngineWidgets`) with external browser fallback

## Behavior Contract

`open_screen_preview(...)` flow:

1. Resolve target preview host directory:
- priority: `run_preview_host_dir` > `run_summary_file` > default config (`preview-host`)
2. Load manifest from `<preview-host>/src/manifest/screens.manifest.json`
3. Validate selected `screenId` exists in manifest
4. Start preview host process if needed:
- default command: `npm run dev -- --host <host> --port <port> --strictPort`
- health check endpoint: `GET /` on configured host/port
5. Build URL: `http://<host>:<port>/preview/<screenId>`
6. Open preview URL:
- `embedded` when Qt WebEngine is available in the running desktop process
- `external` browser fallback otherwise

No screen IDs or sample routes are hardcoded; all screen resolution is manifest-driven.

## Failure Handling

### Directory/manifest failures

- Missing preview host directory -> `FileNotFoundError`
- Missing summary or missing `stages.sync_preview.manifest_file` -> `PreviewBridgeError`
- Missing manifest file -> `FileNotFoundError`

### Selection failures

- Unknown `screenId` -> `PreviewScreenSelectionError` with available screen list

### Process failures

- Launch executable missing (`node`/`npm`) -> `PreviewHostProcessError`
- Process exits before healthy -> `PreviewHostProcessError`
- Health timeout -> `PreviewHostStartTimeoutError`
- Recent process logs are tailed from `.mifl-preview-host.log` to aid diagnosis

### Open failures

- Embedded view unavailable: automatic fallback to external browser
- External browser open failure -> `PreviewBridgeError`

## Desktop Integration Notes

- Keep one bridge instance per desktop app runtime and reuse it across preview opens.
- On desktop app shutdown, call `stop_preview_host()` for deterministic process cleanup.
- For per-job isolated outputs, pass `run_summary_file` from the current run result to avoid stale previews.
