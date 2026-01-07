import { defineConfig, devices } from "@playwright/test";

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
    baseURL: "http://127.0.0.1:5173",
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
      use: { baseURL: "http://127.0.0.1:8000" },
    },
    {
      name: "db",
      testDir: "specs/db",
      use: { baseURL: "http://127.0.0.1:8000" },
    },
  ],
});
