# Preview Host Scaffold (R05)

Minimal Vite + React host to render generated screens through a manifest contract.

## Run

```bash
npm install
npm run dev
```

Open:

- `http://localhost:5173/`
- `http://localhost:5173/preview/simple_screen`

## Contract Summary

- Route shape: `/preview/:screenId`
- Manifest: `src/manifest/screens.manifest.json`
- Schema: `src/manifest/screens.manifest.schema.json`
- Loader registry: `src/screens/registry.ts`
- Screen entry module contract: default export React component receiving `manifestEntry` prop
