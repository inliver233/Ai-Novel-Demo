import fs from "node:fs";
import path from "node:path";

function hasRepoMarkers(dir: string): boolean {
  return fs.existsSync(path.join(dir, "backend")) && fs.existsSync(path.join(dir, "frontend"));
}

export function findRepoRoot(startDir: string): string {
  let current = path.resolve(startDir);
  for (let i = 0; i < 10; i += 1) {
    if (hasRepoMarkers(current)) return current;
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }
  throw new Error(
    `Cannot locate repo root from ${startDir}. Expected to find both 'backend/' and 'frontend/' directories.`,
  );
}

