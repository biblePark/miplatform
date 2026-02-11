import type { ScreenModuleLoader } from "../manifest/types";

export const screenModuleLoaders: Record<string, ScreenModuleLoader> = {
  "screens/placeholder/PlaceholderScreen": () =>
    import("./placeholder/PlaceholderScreen"),
};
