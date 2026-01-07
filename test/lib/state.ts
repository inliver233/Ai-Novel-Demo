import fs from "node:fs";
import path from "node:path";

export type E2EState = {
  repoRoot: string;
  frontendUrl: string;
  backendUrl: string;
  mockLlmBaseUrl: string;
  dbPath: string;
  artifactsDir: string;
  pids: {
    mockLlm?: number;
    backend?: number;
    frontend?: number;
  };
};

const STATE_FILE = path.join(process.cwd(), ".tmp", "state.json");

export function stateFilePath(): string {
  return STATE_FILE;
}

export function loadState(): E2EState {
  const raw = fs.readFileSync(STATE_FILE, "utf-8");
  return JSON.parse(raw) as E2EState;
}

export function saveState(state: E2EState): void {
  fs.mkdirSync(path.dirname(STATE_FILE), { recursive: true });
  fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2), "utf-8");
}

