import os from "node:os";
import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Proxies /api to the FastAPI backend (http://localhost:8000, or API_PROXY_TARGET — the E2E
// suite runs its own backend on another port) during development so the frontend never
// needs CORS config or a hardcoded backend URL.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "src/test/setup.ts",
    css: false,
    // Page tests chain several mocked requests and re-renders; with every file running in
    // parallel (CI's small runners especially), the 5 s default times some of them out.
    testTimeout: 15_000,
    // Each worker holds its own jsdom + React + MSW, so memory, not cores, is the limit: the
    // default (one worker per core) swaps a many-core, little-RAM machine (WSL) into timeouts.
    // Beyond 4 the suite gets no faster. `--maxWorkers=N` on the CLI still overrides this.
    maxWorkers: Math.max(1, Math.min(4, os.availableParallelism() - 1)),
  },
  server: {
    proxy: {
      "/api": {
        target: process.env.API_PROXY_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
