import { test, expect } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";
import { spawnSync } from "node:child_process";

import { loadState } from "../../lib/state";

test("db: schema matches baseline snapshot", async () => {
  const state = loadState();
  const python =
    process.platform === "win32"
      ? path.join(state.repoRoot, "backend", ".venv", "Scripts", "python.exe")
      : path.join(state.repoRoot, "backend", ".venv", "bin", "python");
  const script = path.join(process.cwd(), "scripts", "db_schema_snapshot.py");
  const baseline = path.join(process.cwd(), "contracts", "db_schema.json");

  expect(fs.existsSync(python)).toBeTruthy();
  expect(fs.existsSync(script)).toBeTruthy();
  expect(fs.existsSync(baseline)).toBeTruthy();

  const res = spawnSync(python, [script, "check", "--db", state.dbPath, "--baseline", baseline], {
    encoding: "utf-8",
  });
  if (res.status !== 0) {
    // Surface diff to the Playwright report.
    // eslint-disable-next-line no-console
    console.error(res.stdout || "");
    // eslint-disable-next-line no-console
    console.error(res.stderr || "");
  }
  expect(res.status).toBe(0);
});
