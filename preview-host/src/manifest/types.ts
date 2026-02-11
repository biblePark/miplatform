import type { ComponentType } from "react";

export interface ScreenManifestEntry {
  screenId: string;
  title?: string;
  entryModule: string;
  sourceXmlPath: string;
  sourceNodePath: string;
}

export interface ScreensManifest {
  schemaVersion: "1.0";
  generatedAtUtc: string;
  screens: ScreenManifestEntry[];
}

export interface PreviewScreenProps {
  manifestEntry: ScreenManifestEntry;
}

export type PreviewScreenComponent = ComponentType<PreviewScreenProps>;

export interface PreviewScreenModule {
  default: PreviewScreenComponent;
}

export type ScreenModuleLoader = () => Promise<PreviewScreenModule>;
