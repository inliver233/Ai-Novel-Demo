import { defineConfig, devices } from "@playwright/test";

const frontendUrl = process.env.E2E_FRONTEND_URL ?? "http://127.0.0.1:5173";

export default defineConfig({
  testDir: "./perf",
  fullyParallel: false,
  workers: 1,
  timeout: 600_000,
  expect: {
    timeout: 30_000,
  },
  reporter: [["list"]],
  outputDir: ".artifacts/perf-results",
  globalSetup: "./global-setup",
  globalTeardown: "./global-teardown",
  use: {
    baseURL: frontendUrl,
    viewport: { width: 1280, height: 720 },
    colorScheme: "light",
    reducedMotion: "reduce",
    trace: "off",
    screenshot: "off",
    video: "off",
  },
  projects: [
    {
      name: "ui-perf",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
