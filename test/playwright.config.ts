import { defineConfig, devices } from "@playwright/test";

const frontendUrl = process.env.E2E_FRONTEND_URL ?? "http://127.0.0.1:5173";
const backendUrl = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  testDir: "./specs",
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  expect: {
    timeout: 15_000,
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.01,
    },
  },
  reporter: [
    ["list"],
    [
      "html",
      {
        open: "never",
        outputFolder: ".artifacts/playwright-report",
      },
    ],
  ],
  outputDir: ".artifacts/test-results",
  globalSetup: "./global-setup",
  globalTeardown: "./global-teardown",
  use: {
    baseURL: frontendUrl,
    viewport: { width: 1280, height: 720 },
    colorScheme: "light",
    reducedMotion: "reduce",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "ui-chromium",
      testDir: "specs/ui",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "api",
      testDir: "specs/api",
      use: { baseURL: backendUrl },
    },
    {
      name: "db",
      testDir: "specs/db",
      use: { baseURL: backendUrl },
    },
  ],
});
