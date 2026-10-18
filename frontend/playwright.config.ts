import { fileURLToPath } from "node:url";

import { defineConfig, devices } from "@playwright/test";

// End-to-end: the real API (SQLite + deterministic demo data, no network, no paid APIs) behind
// the production build served by `vite preview`, which proxies /api like nginx does.
const localVenvPython = fileURLToPath(new URL("../backend/.venv/Scripts/python.exe", import.meta.url));
const python = process.env.E2E_PYTHON ?? (process.platform === "win32" ? `"${localVenvPython}"` : "python");

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: { baseURL: "http://127.0.0.1:4173", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `${python} scripts/e2e_server.py 8000`,
      cwd: "../backend",
      url: "http://127.0.0.1:8000/api/v1/health/ready",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "npm run build && npx vite preview --host 127.0.0.1 --port 4173 --strictPort",
      env: { VITE_API_PROXY_TARGET: "http://127.0.0.1:8000" },
      url: "http://127.0.0.1:4173",
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
});
