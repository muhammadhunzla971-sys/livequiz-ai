import { defineConfig } from '@playwright/test'

// Runs against a live stack: `docker compose up -d` (API on :8000) + the Vite dev server.
// Override with E2E_BASE (frontend) and E2E_API (backend) to test another deployment.
export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: process.env.E2E_BASE ?? 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    launchOptions: process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {},
  },
  webServer: process.env.E2E_BASE
    ? undefined
    : {
        command: 'npm run dev -- --host 127.0.0.1',
        url: 'http://127.0.0.1:5173',
        reuseExistingServer: true,
      },
})
