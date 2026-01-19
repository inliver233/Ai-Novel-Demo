import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };
type ApiErr = { ok: false; error: { code: string; message: string; details?: Record<string, unknown> }; request_id: string };

test("api: worldbook export_all + import_all (dry_run + apply) contract", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  for (const title of ["Dragon", "Castle"]) {
    const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries`, {
      data: {
        title,
        content_md: `${title} content`,
        enabled: true,
        constant: false,
        keywords: [title.toLowerCase()],
        exclude_recursion: false,
        prevent_recursion: false,
        char_limit: 12000,
        priority: "important",
      },
    });
    expect(create.ok()).toBeTruthy();
  }

  const exportRes = await request.get(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries/export_all`);
  expect(exportRes.ok()).toBeTruthy();
  const exportJson = (await exportRes.json()) as ApiOk<{
    export: {
      schema_version: string;
      entries: Array<{
        title: string;
        content_md: string;
        enabled: boolean;
        constant: boolean;
        keywords: string[];
        exclude_recursion: boolean;
        prevent_recursion: boolean;
        char_limit: number;
        priority: string;
      }>;
    };
  }>;
  expect(exportJson.ok).toBe(true);
  expect(typeof exportJson.request_id).toBe("string");
  expect(exportJson.data.export.schema_version).toBe("worldbook_export_all_v1");
  expect(exportJson.data.export.entries.some((e) => e.title === "Dragon")).toBe(true);
  expect(exportJson.data.export.entries.some((e) => e.title === "Castle")).toBe(true);

  const badSchemaRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries/import_all`, {
    data: {
      schema_version: "unknown_schema",
      mode: "merge",
      dry_run: true,
      entries: [],
    },
  });
  expect(badSchemaRes.ok()).toBe(false);
  expect(badSchemaRes.status()).toBe(400);
  const badSchemaJson = (await badSchemaRes.json()) as ApiErr;
  expect(badSchemaJson.ok).toBe(false);
  expect(badSchemaJson.error.code).toBe("VALIDATION_ERROR");
  expect(String(badSchemaJson.error.details?.reason ?? "")).toBe("unsupported_schema_version");

  const incoming = [
    {
      title: "Dragon",
      content_md: "Fire v2.",
      enabled: true,
      constant: false,
      keywords: ["dragon"],
      exclude_recursion: false,
      prevent_recursion: false,
      char_limit: 12000,
      priority: "important",
    },
    {
      title: "NewEntry",
      content_md: "New content.",
      enabled: true,
      constant: false,
      keywords: ["new"],
      exclude_recursion: false,
      prevent_recursion: false,
      char_limit: 12000,
      priority: "important",
    },
  ];

  const importDryRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries/import_all`, {
    data: {
      schema_version: "worldbook_export_all_v1",
      mode: "merge",
      dry_run: true,
      entries: incoming,
    },
  });
  expect(importDryRes.ok()).toBeTruthy();
  const importDryJson = (await importDryRes.json()) as ApiOk<{
    dry_run: boolean;
    mode: string;
    created: number;
    updated: number;
    deleted: number;
    skipped: number;
  }>;
  expect(importDryJson.data.dry_run).toBe(true);
  expect(importDryJson.data.mode).toBe("merge");
  expect(importDryJson.data.created).toBe(1);
  expect(importDryJson.data.updated).toBe(1);
  expect(importDryJson.data.deleted).toBe(0);

  const importApplyRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries/import_all`, {
    data: {
      schema_version: "worldbook_export_all_v1",
      mode: "merge",
      dry_run: false,
      entries: incoming,
    },
  });
  expect(importApplyRes.ok()).toBeTruthy();
  const importApplyJson = (await importApplyRes.json()) as ApiOk<{
    dry_run: boolean;
    mode: string;
    created: number;
    updated: number;
    deleted: number;
    skipped: number;
  }>;
  expect(importApplyJson.data.dry_run).toBe(false);
  expect(importApplyJson.data.mode).toBe("merge");
  expect(importApplyJson.data.created).toBe(1);
  expect(importApplyJson.data.updated).toBe(1);

  const listRes = await request.get(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries`);
  expect(listRes.ok()).toBeTruthy();
  const listJson = (await listRes.json()) as ApiOk<{ worldbook_entries: Array<{ title: string; content_md: string }> }>;
  const byTitle = new Map(listJson.data.worldbook_entries.map((e) => [e.title, e]));
  expect(byTitle.get("Dragon")?.content_md).toBe("Fire v2.");
  expect(byTitle.has("NewEntry")).toBe(true);

  // Must not leak api keys or secrets (bootstrapProject uses "test-key").
  const raw = JSON.stringify(exportJson) + JSON.stringify(importApplyJson);
  expect(raw).not.toContain("test-key");
  expect(raw).not.toMatch(/sk-[a-zA-Z0-9]{10,}/);
});

