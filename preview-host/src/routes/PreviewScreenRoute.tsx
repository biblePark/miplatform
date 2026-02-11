import { Suspense, lazy, useMemo } from "react";
import { useParams } from "react-router-dom";

import { PreviewHostShell } from "../app/PreviewHostShell";
import type { ScreenModuleLoader, ScreensManifest } from "../manifest/types";

interface PreviewScreenRouteProps {
  manifest: ScreensManifest;
  loaders: Record<string, ScreenModuleLoader>;
}

export function PreviewScreenRoute({ manifest, loaders }: PreviewScreenRouteProps) {
  const { screenId } = useParams<{ screenId: string }>();
  const screenEntry = manifest.screens.find((item) => item.screenId === screenId);

  if (!screenId || !screenEntry) {
    return (
      <PreviewHostShell
        title="Screen Not Found"
        subtitle="Requested screenId is not present in screens manifest."
      >
        <p>
          Requested <code>screenId</code>: {screenId ?? "(empty)"}
        </p>
      </PreviewHostShell>
    );
  }

  const loader = loaders[screenEntry.entryModule];
  if (!loader) {
    return (
      <PreviewHostShell
        title="Loader Not Registered"
        subtitle="Manifest entryModule exists, but no loader is registered in registry.ts."
      >
        <p>
          Missing loader key: <code>{screenEntry.entryModule}</code>
        </p>
      </PreviewHostShell>
    );
  }

  const ScreenComponent = useMemo(() => lazy(loader), [loader]);

  return (
    <PreviewHostShell
      title={`Preview: ${screenEntry.title ?? screenEntry.screenId}`}
      subtitle="Manifest-resolved route rendering"
    >
      <Suspense fallback={<p>Loading screen module...</p>}>
        <ScreenComponent manifestEntry={screenEntry} />
      </Suspense>
    </PreviewHostShell>
  );
}
