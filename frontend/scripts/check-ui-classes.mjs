import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const projectRoot = process.cwd();
const srcRoot = path.join(projectRoot, "src");

const variantTokens = new Set(["btn-primary", "btn-secondary", "btn-ghost", "btn-danger"]);

function walk(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const out = [];
  for (const ent of entries) {
    const full = path.join(dir, ent.name);
    if (ent.isDirectory()) out.push(...walk(full));
    else out.push(full);
  }
  return out;
}

function lineColFromIndex(text, index) {
  const before = text.slice(0, index);
  const lines = before.split("\n");
  const line = lines.length;
  const col = lines[lines.length - 1].length + 1;
  return { line, col };
}

const issues = [];
const files = walk(srcRoot).filter((p) => p.endsWith(".ts") || p.endsWith(".tsx"));

for (const filePath of files) {
  const raw = fs.readFileSync(filePath, "utf-8");
  const rx = /\bclassName\s*=\s*"([^"]*)"/g;
  let match;
  while ((match = rx.exec(raw))) {
    const classValue = match[1];
    const tokens = classValue
      .split(/\s+/)
      .map((t) => t.trim())
      .filter(Boolean);
    const hasBtn = tokens.includes("btn");
    const hasVariant = tokens.some((t) => variantTokens.has(t));
    if (!hasBtn && !hasVariant) continue;

    const rel = path.relative(projectRoot, filePath);
    const { line, col } = lineColFromIndex(raw, match.index);

    if (hasVariant && !hasBtn) {
      issues.push({
        rel,
        line,
        col,
        message: `className=\"${classValue}\" uses btn-* without base "btn"`,
      });
      continue;
    }

    if (hasBtn && !hasVariant) {
      issues.push({
        rel,
        line,
        col,
        message: `className=\"${classValue}\" uses "btn" without a variant (btn-primary/secondary/ghost/danger)`,
      });
    }
  }
}

if (issues.length) {
  // Keep output stable and grep-friendly for CI.
  for (const it of issues) {
    console.error(`[ui-class-guard] ${it.rel}:${it.line}:${it.col} ${it.message}`);
  }
  process.exit(1);
}
