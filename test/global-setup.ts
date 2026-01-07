import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

import type { FullConfig } from "@playwright/test";

import { findRepoRoot } from "./lib/paths";
import { assertPortFree, waitForHttpOk } from "./lib/net";
import { nodeCommand, npmCommand, spawnLogged } from "./lib/proc";
import { saveState, type E2EState } from "./lib/state";

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

export default async function globalSetup(_config: FullConfig): Promise<void> {
  const spawnedPids: number[] = [];
  try {
    const testDir = process.cwd();
    const repoRoot = findRepoRoot(testDir);

    const backendPort = 8000;
    const frontendPort = 5173;
    const mockPort = 4010;

    await assertPortFree(mockPort);
    await assertPortFree(backendPort);
    await assertPortFree(frontendPort);

    const artifactsDir = path.join(testDir, ".artifacts");
    fs.mkdirSync(artifactsDir, { recursive: true });

    const backendDir = path.join(repoRoot, "backend");
    const frontendDir = path.join(repoRoot, "frontend");
    const mockLlmScript = path.join(testDir, "mock-llm", "server.js");

    const backendTmpDir = path.join(backendDir, ".tmp_test");
    fs.mkdirSync(backendTmpDir, { recursive: true });
    const dbPath = path.join(backendTmpDir, "ainovel.e2e.db");
    for (const suffix of ["", "-wal", "-shm", "-journal"]) {
      const p = `${dbPath}${suffix}`;
      if (fs.existsSync(p)) fs.rmSync(p, { force: true });
    }

    const mockLlm = spawnLogged({
      name: "mock-llm",
      cwd: testDir,
      command: nodeCommand(),
      commandArgs: [mockLlmScript],
      env: {
        PORT: String(mockPort),
      },
      logFile: path.join(artifactsDir, "mock-llm.log"),
    });
    spawnedPids.push(mockLlm.pid ?? 0);
    await waitForHttpOk(`http://127.0.0.1:${mockPort}/health`, { timeoutMs: 20_000 });

    const python =
      process.platform === "win32"
        ? path.join(backendDir, ".venv", "Scripts", "python.exe")
        : path.join(backendDir, ".venv", "bin", "python");
    if (!fs.existsSync(python)) {
      throw new Error(`Backend venv python not found at: ${python}\nRun backend setup first (see README.md).`);
    }

    const backend = spawnLogged({
      name: "backend",
      cwd: backendDir,
      command: python,
      commandArgs: ["-m", "uvicorn", "app.main:app", "--workers", "1", "--port", String(backendPort)],
      env: {
        APP_ENV: "dev",
        LOG_LEVEL: "INFO",
        TASK_QUEUE_BACKEND: "inline",
        DATABASE_URL: "sqlite:///./.tmp_test/ainovel.e2e.db",
        CORS_ORIGINS: `http://localhost:${frontendPort},http://127.0.0.1:${frontendPort}`,
        PYTHONUNBUFFERED: "1",
      },
      logFile: path.join(artifactsDir, "backend.log"),
    });
    spawnedPids.push(backend.pid ?? 0);
    await waitForHttpOk(`http://127.0.0.1:${backendPort}/api/health`, { timeoutMs: 60_000 });

    const frontendCommand = process.platform === "win32" ? "cmd.exe" : npmCommand();
    const frontendCommandArgs = process.platform === "win32" ? ["/c", npmCommand(), "run", "dev"] : ["run", "dev"];
    const frontend = spawnLogged({
      name: "frontend",
      cwd: frontendDir,
      command: frontendCommand,
      commandArgs: frontendCommandArgs,
      env: {
        // Make sure Vite uses a stable URL in tests.
        HOST: "127.0.0.1",
      },
      logFile: path.join(artifactsDir, "frontend.log"),
    });
    spawnedPids.push(frontend.pid ?? 0);
    await waitForHttpOk(`http://127.0.0.1:${frontendPort}/`, { timeoutMs: 60_000 });

    const state: E2EState = {
      repoRoot,
      frontendUrl: `http://127.0.0.1:${frontendPort}`,
      backendUrl: `http://127.0.0.1:${backendPort}`,
      mockLlmBaseUrl: `http://127.0.0.1:${mockPort}/v1`,
      dbPath,
      artifactsDir,
      pids: {
        mockLlm: mockLlm.pid ?? undefined,
        backend: backend.pid ?? undefined,
        frontend: frontend.pid ?? undefined,
      },
    };
    saveState(state);
  } catch (err) {
    for (const pid of spawnedPids.reverse()) killPid(pid);
    throw err;
  }
}
