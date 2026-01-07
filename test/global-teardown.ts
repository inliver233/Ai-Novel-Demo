import fs from "node:fs";
import { execFileSync } from "node:child_process";

import { loadState, stateFilePath } from "./lib/state";

function killPid(pid: number): void {
  if (!pid) return;
  try {
    if (process.platform === "win32") {
      execFileSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" });
      return;
    }
    process.kill(pid, "SIGTERM");
  } catch {
    // ignore
  }
}

export default async function globalTeardown(): Promise<void> {
  const statePath = stateFilePath();
  if (!fs.existsSync(statePath)) return;
  const state = loadState();

  killPid(state.pids.frontend ?? 0);
  killPid(state.pids.backend ?? 0);
  killPid(state.pids.mockLlm ?? 0);
}

