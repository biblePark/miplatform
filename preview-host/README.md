# Preview Host Scaffold (R05-R06)

Minimal Vite + React host to render generated screens through a manifest contract.

## Run

```bash
npm install
npm run dev
```

Open:

- `http://localhost:5173/`
- `http://localhost:5173/preview/simple_screen`

## Sync Generated Outputs (R06)

Refresh `preview-host` manifest + generated registry after UI codegen output changes:

```bash
PYTHONPATH=src python3 -m migrator sync-preview --generated-screens-dir generated/frontend/src/screens --preview-host-dir preview-host --report-out out/preview-sync-report.json --pretty
```

Generated registry file:

- `src/screens/registry.generated.ts` (auto-written, do not edit manually)

Optional per-screen metadata sidecar:

- `<ScreenModule>.preview.json`
- Supported fields: `screenId`, `title`, `sourceXmlPath`, `sourceNodePath`

## Local Verification Flow

1. Generate or update UI screen modules under `generated/frontend/src/screens`.
2. Run `mifl-migrator sync-preview` (command above).
3. Build host:

```bash
cd preview-host
npm install
npm run build
```

4. Run dev host and open a generated route:

```bash
npm run dev
```

Open `http://localhost:5173/preview/<screenId>` using any screen ID present in `src/manifest/screens.manifest.json`.

## Contract Summary

- Route shape: `/preview/:screenId`
- Manifest: `src/manifest/screens.manifest.json`
- Schema: `src/manifest/screens.manifest.schema.json`
- Loader registry: `src/screens/registry.ts`
- Screen entry module contract: default export React component receiving `manifestEntry` prop
