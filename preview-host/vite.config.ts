import { defineConfig, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";

const studioApiTarget = process.env.MIFL_STUDIO_API_TARGET ?? "http://127.0.0.1:8765";
const adapterApiPrefixes = ["/jobs", "/health", "/api/studio"] as const;

const studioApiProxy = adapterApiPrefixes.reduce<Record<string, ProxyOptions>>(
  (accumulator, prefix) => {
    accumulator[prefix] = {
      target: studioApiTarget,
      changeOrigin: true,
    };
    return accumulator;
  },
  {},
);

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: studioApiProxy,
  },
});
