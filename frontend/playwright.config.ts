import { defineConfig } from "@playwright/test";
import { ADMIN_PASSWORD } from "./e2e/credentials";

// End-to-end journeys against the real stack: the FastAPI backend on a throwaway SQLite
// file seeded with the synthetic consultations, the fake chat LLM (scripts/fake_llm_server.py)
// and the Vite dev server. Own ports, so it never collides with `make dev`.
// Retrieval embeddings still hit the real Mistral API (backend/.env needs MISTRAL_API_KEY and
// DB_PATH), which is why this is not part of `npm test` or the PR checks — run `npm run e2e`.
const BACKEND_PORT = 8010;
const FAKE_LLM_PORT = 8081;
const FRONTEND_PORT = 5174;

export default defineConfig({
  testDir: "e2e",
  testMatch: "*.e2e.ts",
  // The journeys share one seeded database and build on its state in order.
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 20_000 },
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${FRONTEND_PORT}`,
    locale: "fr-CA",
    timezoneId: "America/Montreal",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
  webServer: [
    {
      command: `uv run python scripts/fake_llm_server.py --port ${FAKE_LLM_PORT}`,
      cwd: "../backend",
      url: `http://localhost:${FAKE_LLM_PORT}/docs`,
      reuseExistingServer: false,
    },
    {
      // Wipe and reseed first: the schema has no migrations and the tests expect the 25
      // untouched "reçu" encounters.
      command: [
        "rm -f e2e.db",
        "uv run python scripts/seed_db.py > /dev/null",
        `uv run uvicorn app.main:app --port ${BACKEND_PORT}`,
      ].join(" && "),
      cwd: "../backend",
      url: `http://localhost:${BACKEND_PORT}/health`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        DATABASE_URL: "sqlite+aiosqlite:///./e2e.db",
        SEED_ADMIN_PASSWORD: ADMIN_PASSWORD,
        LLM_PROVIDER: "openai_compatible",
        LLM_ENDPOINT: `http://localhost:${FAKE_LLM_PORT}/v1`,
        LLM_API_KEY: "fake",
        COOKIE_SECURE: "false",
        EPIC_SANDBOX_ENABLED: "false",
      },
    },
    {
      command: `npm run dev -- --port ${FRONTEND_PORT} --strictPort`,
      url: `http://localhost:${FRONTEND_PORT}`,
      reuseExistingServer: false,
      env: { API_PROXY_TARGET: `http://localhost:${BACKEND_PORT}` },
    },
  ],
});
