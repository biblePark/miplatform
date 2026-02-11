import type { ScreenModuleLoader } from "../manifest/types";
import { generatedScreenModuleLoaders } from "./registry.generated";

const manualScreenModuleLoaders: Record<string, ScreenModuleLoader> = {
  "screens/placeholder/PlaceholderScreen": () =>
    import("./placeholder/PlaceholderScreen"),
};

export const screenModuleLoaders: Record<string, ScreenModuleLoader> = {
  ...manualScreenModuleLoaders,
  ...generatedScreenModuleLoaders,
};
