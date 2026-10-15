import { defineConfig } from "@playwright/test";

// E2E contra la app en ejecución (frontend :3000 + backend :8000 con AI_PROVIDER=demo o Claude Code con sesión iniciada).
// Por defecto usa el navegador Microsoft Edge/Chrome instalado en el sistema (sin descargas).
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    channel: process.env.E2E_BROWSER_CHANNEL ?? "msedge",
    headless: true,
    viewport: { width: 1366, height: 900 },
    acceptDownloads: true,
    trace: "retain-on-failure",
  },
});
