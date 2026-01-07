import fs from "node:fs";
import path from "node:path";
import { spawn, type ChildProcess } from "node:child_process";

function bin(name: string): string {
  if (process.platform === "win32") {
    if (name === "npm") return "npm.cmd";
    if (name === "npx") return "npx.cmd";
  }
  return name;
}

export function spawnLogged(args: {
  name: string;
  cwd: string;
  command: string;
  commandArgs: string[];
  env?: Record<string, string | undefined>;
  logFile: string;
  shell?: boolean;
}): ChildProcess {
  fs.mkdirSync(path.dirname(args.logFile), { recursive: true });
  const out = fs.createWriteStream(args.logFile, { flags: "a" });
  out.write(`[${new Date().toISOString()}] START ${args.name}\n`);
  out.write(`cwd=${args.cwd}\n`);
  out.write(`cmd=${args.command} ${args.commandArgs.join(" ")}\n\n`);

  const child = spawn(args.command, args.commandArgs, {
    cwd: args.cwd,
    env: { ...process.env, ...args.env },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
    shell: args.shell ?? false,
  });
  child.stdout?.pipe(out);
  child.stderr?.pipe(out);
  child.on("exit", (code, signal) => {
    out.write(`\n[${new Date().toISOString()}] EXIT ${args.name} code=${code ?? "null"} signal=${signal ?? "null"}\n`);
  });
  return child;
}

export function npmCommand(): string {
  return bin("npm");
}

export function nodeCommand(): string {
  return process.execPath;
}
