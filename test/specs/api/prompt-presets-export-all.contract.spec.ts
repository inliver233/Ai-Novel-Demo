import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("api: prompt_presets export_all + import_all contract", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const exportRes = await request.get(`${state.backendUrl}/api/projects/${projectId}/prompt_presets/export_all`);
  expect(exportRes.ok()).toBeTruthy();
  const exportJson = (await exportRes.json()) as ApiOk<{ export: any }>;
  expect(exportJson.ok).toBe(true);

  const exportObj = exportJson.data.export as { schema_version?: unknown; presets?: unknown };
  expect(exportObj.schema_version).toBe("prompt_presets_export_all_v1");
  expect(Array.isArray(exportObj.presets)).toBe(true);

  const presets = exportObj.presets as Array<{ preset?: any; blocks?: any }>;
  expect(presets.length).toBeGreaterThan(0);

  const first = presets[0];
  expect(first && typeof first === "object").toBe(true);
  expect(first).toHaveProperty("preset");
  expect(first).toHaveProperty("blocks");

  const preset = first.preset as {
    name?: unknown;
    category?: unknown;
    scope?: unknown;
    version?: unknown;
    active_for?: unknown;
  };
  expect(typeof preset.name).toBe("string");
  expect(preset.category === null || preset.category === undefined || typeof preset.category === "string").toBe(true);
  expect(typeof preset.scope).toBe("string");
  expect(typeof preset.version).toBe("number");
  expect(Array.isArray(preset.active_for)).toBe(true);

  const blocks = first.blocks as unknown;
  expect(Array.isArray(blocks)).toBe(true);
  if (Array.isArray(blocks) && blocks.length) {
    const b = blocks[0] as Record<string, unknown>;
    for (const k of [
      "identifier",
      "name",
      "role",
      "enabled",
      "template",
      "marker_key",
      "injection_position",
      "injection_depth",
      "injection_order",
      "triggers",
      "forbid_overrides",
      "budget",
      "cache",
    ]) {
      expect(b).toHaveProperty(k);
    }
    expect(Array.isArray(b.triggers)).toBe(true);
    expect(typeof b.enabled).toBe("boolean");
    expect(typeof b.forbid_overrides).toBe("boolean");
  }

  const uniqueName = `E2E ImportAll ${Date.now()}`;
  const importBody = {
    schema_version: "prompt_presets_export_all_v1",
    dry_run: true,
    presets: [
      {
        preset: { name: uniqueName, category: "E2E", scope: "project", version: 1, active_for: [] },
        blocks: [],
      },
    ],
  };

  const importRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/prompt_presets/import_all`, {
    data: importBody,
  });
  expect(importRes.ok()).toBeTruthy();
  const importJson = (await importRes.json()) as ApiOk<{
    dry_run: boolean;
    created: number;
    updated: number;
    skipped: number;
    conflicts: unknown[];
    actions: unknown[];
  }>;
  expect(importJson.ok).toBe(true);
  expect(importJson.data.dry_run).toBe(true);
  expect(Number.isInteger(importJson.data.created)).toBe(true);
  expect(importJson.data.created).toBeGreaterThanOrEqual(1);
  expect(Number.isInteger(importJson.data.updated)).toBe(true);
  expect(Number.isInteger(importJson.data.skipped)).toBe(true);
  expect(Array.isArray(importJson.data.conflicts)).toBe(true);
  expect(Array.isArray(importJson.data.actions)).toBe(true);
});

