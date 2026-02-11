import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import manifestJson from "../manifest/screens.manifest.json";
import {
  ManifestContractError,
  loadScreensManifest,
} from "../manifest/loadScreensManifest";
import { screenModuleLoaders } from "../screens/registry";
import { PreviewHostShell } from "./PreviewHostShell";
import { PreviewScreenRoute } from "../routes/PreviewScreenRoute";

type ManifestBootstrap =
  | { error: null; manifest: ReturnType<typeof loadScreensManifest> }
  | { error: string; manifest: null };

function bootstrapManifest(): ManifestBootstrap {
  try {
    return { error: null, manifest: loadScreensManifest(manifestJson) };
  } catch (error) {
    if (error instanceof ManifestContractError) {
      return { error: error.message, manifest: null };
    }
    return { error: `Unexpected manifest bootstrap error: ${String(error)}`, manifest: null };
  }
}

export function PreviewApp() {
  const bootstrap = bootstrapManifest();
  if (bootstrap.error) {
    return (
      <PreviewHostShell
        title="Manifest Contract Error"
        subtitle="Preview Host could not load screens manifest."
      >
        <p>{bootstrap.error}</p>
      </PreviewHostShell>
    );
  }

  const defaultScreen = bootstrap.manifest.screens[0];
  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/"
          element={
            defaultScreen ? (
              <Navigate to={`/preview/${defaultScreen.screenId}`} replace />
            ) : (
              <PreviewHostShell
                title="No Screens Registered"
                subtitle="Manifest loaded successfully but screens[] is empty."
              >
                <p>Add at least one screen entry to render preview routes.</p>
              </PreviewHostShell>
            )
          }
        />
        <Route
          path="/preview/:screenId"
          element={
            <PreviewScreenRoute
              manifest={bootstrap.manifest}
              loaders={screenModuleLoaders}
            />
          }
        />
        <Route
          path="*"
          element={
            <PreviewHostShell
              title="Route Not Found"
              subtitle="Only / and /preview/:screenId routes are supported."
            >
              <p>Use a registered screenId from the manifest.</p>
            </PreviewHostShell>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
