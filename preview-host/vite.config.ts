import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const studioApiTarget = process.env.MIFL_STUDIO_API_TARGET ?? "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/jobs": {
        target: studioApiTarget,
        changeOrigin: true,
      },
      "/health": {
        target: studioApiTarget,
        changeOrigin: true,
      },
      "/api/studio": {
        target: studioApiTarget,
        changeOrigin: true,
      },
    },
  },
});
