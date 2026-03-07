import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

import type { FullConfig } from "@playwright/test";

import { findRepoRoot } from "./lib/paths";
import { assertPortFree, getFreePort, waitForHttpOk } from "./lib/net";
import { nodeCommand, npmCommand, spawnLogged } from "./lib/proc";
import {
  loadState,
  saveState,
  stateFilePath,
  type E2EState,
} from "./lib/state";

function killPid(pid: number): void {
  if (!pid) return;
  try {
    if (process.platform === "win32") {
      execFileSync("taskkill", ["/PID", String(pid), "/T", "/F"], {
        stdio: "ignore",
      });
      return;
    }
    process.kill(pid, "SIGTERM");
  } catch {
    // ignore
  }
}

function parseUrlOrDefault(input: string | undefined, fallback: string): URL {
  try {
    return new URL(input ?? fallback);
  } catch {
    return new URL(fallback);
  }
}

export default async function globalSetup(_config: FullConfig): Promise<void> {
  const spawnedPids: number[] = [];
  try {
    const testDir = process.cwd();
    const repoRoot = findRepoRoot(testDir);

    // Best-effort cleanup: previous run might have crashed before globalTeardown.
    // Kill old pids first so port checks can recover automatically.
    const prevStatePath = stateFilePath();
    if (fs.existsSync(prevStatePath)) {
      try {
        const prev = loadState();
        killPid(prev.pids.frontend ?? 0);
        killPid(prev.pids.backend ?? 0);
        killPid(prev.pids.mockLlm ?? 0);
      } catch {
        // ignore (corrupted state file, etc.)
      }
    }

    const backendConfig = parseUrlOrDefault(
      process.env.E2E_BACKEND_URL,
      "http://127.0.0.1:8000",
    );
    const frontendConfig = parseUrlOrDefault(
      process.env.E2E_FRONTEND_URL,
      "http://127.0.0.1:5173",
    );
    const mockPort = Number(process.env.E2E_MOCK_PORT || 4010);

    const backendPort = Number(backendConfig.port || 8000);
    const frontendPort = Number(frontendConfig.port || 5173);
    const backendUrl = `http://${backendConfig.hostname}:${backendPort}`;
    const frontendUrl = `http://${frontendConfig.hostname}:${frontendPort}`;

    let effectiveMockPort = mockPort;
    try {
      await assertPortFree(mockPort, "127.0.0.1", {
        retries: 20,
        intervalMs: 250,
      });
    } catch {
      // Safe to auto-switch the mock server port because only globalSetup + state.json depend on it.
      const fallback = await getFreePort("127.0.0.1");
      // eslint-disable-next-line no-console
      console.warn(
        `[e2e] Mock LLM port ${mockPort} is in use; falling back to ${fallback}. Set E2E_MOCK_PORT to override.`,
      );
      effectiveMockPort = fallback;
    }

    const suggestedBackendPort = await getFreePort(backendConfig.hostname);
    const suggestedFrontendPort = await getFreePort(frontendConfig.hostname);

    await assertPortFree(backendPort, backendConfig.hostname, {
      retries: 40,
      intervalMs: 250,
      hint: [
        "Tips:",
        "- If this is a stale E2E run, just re-run; globalSetup auto-kills pids from test/.tmp/state.json.",
        "- If port 8000 is used by another app, override ports and retry:",
        `  $env:E2E_BACKEND_URL=\"http://${backendConfig.hostname}:${suggestedBackendPort}\"`,
        `  $env:E2E_FRONTEND_URL=\"http://${frontendConfig.hostname}:${suggestedFrontendPort}\"`,
        "  npm test",
      ].join("\n"),
    });
    await assertPortFree(frontendPort, frontendConfig.hostname, {
      retries: 40,
      intervalMs: 250,
      hint: [
        "Tips:",
        "- If this is a stale E2E run, just re-run; globalSetup auto-kills pids from test/.tmp/state.json.",
        "- If port 5173 is used by another app, override ports and retry:",
        `  $env:E2E_BACKEND_URL=\"http://${backendConfig.hostname}:${suggestedBackendPort}\"`,
        `  $env:E2E_FRONTEND_URL=\"http://${frontendConfig.hostname}:${suggestedFrontendPort}\"`,
        "  npm test",
      ].join("\n"),
    });

    const artifactsDir = path.join(testDir, ".artifacts");
    fs.mkdirSync(artifactsDir, { recursive: true });

    const backendDir = path.join(repoRoot, "backend");
    const frontendDir = path.join(repoRoot, "frontend");
    const mockLlmScript = path.join(testDir, "mock-llm", "server.js");

    const backendTmpDir = path.join(backendDir, ".tmp_test");
    fs.mkdirSync(backendTmpDir, { recursive: true });
    for (const name of fs.readdirSync(backendTmpDir)) {
      if (!name.startsWith("ainovel.e2e")) continue;
      try {
        fs.rmSync(path.join(backendTmpDir, name), { force: true });
      } catch {
        // ignore stale locked files from previous aborted runs
      }
    }
    const dbFileName = `ainovel.e2e.${Date.now()}.db`;
    const dbPath = path.join(backendTmpDir, dbFileName);

    const mockLlm = spawnLogged({
      name: "mock-llm",
      cwd: testDir,
      command: nodeCommand(),
      commandArgs: [mockLlmScript],
      env: {
        PORT: String(effectiveMockPort),
      },
      logFile: path.join(artifactsDir, "mock-llm.log"),
    });
    spawnedPids.push(mockLlm.pid ?? 0);
    await waitForHttpOk(`http://127.0.0.1:${effectiveMockPort}/health`, {
      timeoutMs: 20_000,
    });

    const python =
      process.platform === "win32"
        ? path.join(backendDir, ".venv", "Scripts", "python.exe")
        : path.join(backendDir, ".venv", "bin", "python");
    if (!fs.existsSync(python)) {
      throw new Error(
        `Backend venv python not found at: ${python}\nRun backend setup first (see README.md).`,
      );
    }

    const backend = spawnLogged({
      name: "backend",
      cwd: backendDir,
      command: python,
      commandArgs: [
        "-m",
        "uvicorn",
        "app.main:app",
        "--workers",
        "1",
        "--port",
        String(backendPort),
      ],
      env: {
        APP_ENV: "dev",
        LOG_LEVEL: "INFO",
        TASK_QUEUE_BACKEND: "inline",
        DATABASE_URL: `sqlite:///./.tmp_test/${dbFileName}`,
        CORS_ORIGINS: `http://localhost:${frontendPort},http://127.0.0.1:${frontendPort}`,
        AUTH_ADMIN_USER_ID: "admin",
        AUTH_ADMIN_PASSWORD: "admin-pass",
        VECTOR_PER_SOURCE_ID_MAX_CHUNKS: "3",
        WORLDBOOK_MATCH_ALIAS_ENABLED: "true",
        PYTHONUNBUFFERED: "1",
      },
      logFile: path.join(artifactsDir, "backend.log"),
    });
    spawnedPids.push(backend.pid ?? 0);
    await waitForHttpOk(`${backendUrl}/api/health`, { timeoutMs: 60_000 });

    const frontendCommand =
      process.platform === "win32" ? "cmd.exe" : npmCommand();
    const frontendCommandArgs =
      process.platform === "win32"
        ? ["/c", npmCommand(), "run", "dev"]
        : ["run", "dev"];
    const frontendEnv: Record<string, string | undefined> = {
      // Make sure Vite uses a stable URL in tests.
      HOST: frontendConfig.hostname,
      VITE_DEV_PORT: String(frontendPort),
      VITE_DEV_FALLBACK_ENABLED: "true",
    };
    // Allow overriding backend for external runs, but keep default-path coverage for local E2E.
    if (process.env.E2E_BACKEND_URL)
      frontendEnv.VITE_API_PROXY_TARGET = backendUrl;

    const frontend = spawnLogged({
      name: "frontend",
      cwd: frontendDir,
      command: frontendCommand,
      commandArgs: frontendCommandArgs,
      env: frontendEnv,
      logFile: path.join(artifactsDir, "frontend.log"),
    });
    spawnedPids.push(frontend.pid ?? 0);
    await waitForHttpOk(`${frontendUrl}/`, { timeoutMs: 60_000 });

    const state: E2EState = {
      repoRoot,
      frontendUrl,
      backendUrl,
      mockLlmBaseUrl: `http://127.0.0.1:${effectiveMockPort}/v1`,
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
