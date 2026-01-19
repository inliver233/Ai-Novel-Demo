import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("api: multi-kb CRUD + reorder + query returns per_kb counts", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const settingsRes = await request.put(`${state.backendUrl}/api/projects/${projectId}/settings`, {
    data: {
      vector_embedding_base_url: state.mockLlmBaseUrl,
      vector_embedding_model: "text-embedding-mock",
      vector_embedding_api_key: "test-key",
    },
  });
  expect(settingsRes.ok()).toBeTruthy();

  const wbRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries`, {
    data: {
      title: "E2E MultiKB WB",
      content_md: "dragon dragon dragon",
      enabled: true,
      constant: false,
      keywords: ["dragon"],
      exclude_recursion: false,
      prevent_recursion: false,
      char_limit: 12000,
      priority: "important",
    },
  });
  expect(wbRes.ok()).toBeTruthy();

  const list1 = await request.get(`${state.backendUrl}/api/projects/${projectId}/vector/kbs`);
  expect(list1.ok()).toBeTruthy();
  const list1Json = (await list1.json()) as ApiOk<{ kbs: Array<{ kb_id: string }> }>;
  expect(list1Json.ok).toBe(true);
  expect(list1Json.data.kbs.some((k) => k.kb_id === "default")).toBe(true);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/vector/kbs`, {
    data: { name: "E2E KB", kb_id: "kb_e2e", enabled: true, weight: 3.0 },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as ApiOk<{ kb: { kb_id: string; weight: number; enabled: boolean } }>;
  expect(createJson.ok).toBe(true);
  expect(createJson.data.kb.kb_id).toBe("kb_e2e");
  expect(createJson.data.kb.enabled).toBe(true);

  const update = await request.put(`${state.backendUrl}/api/projects/${projectId}/vector/kbs/kb_e2e`, {
    data: { weight: 2.5 },
  });
  expect(update.ok()).toBeTruthy();
  const updateJson = (await update.json()) as ApiOk<{ kb: { kb_id: string; weight: number } }>;
  expect(updateJson.ok).toBe(true);
  expect(updateJson.data.kb.weight).toBe(2.5);

  const reorder = await request.post(`${state.backendUrl}/api/projects/${projectId}/vector/kbs/reorder`, {
    data: { kb_ids: ["kb_e2e", "default"] },
  });
  expect(reorder.ok()).toBeTruthy();
  const reorderJson = (await reorder.json()) as ApiOk<{ kbs: Array<{ kb_id: string; order: number }> }>;
  expect(reorderJson.ok).toBe(true);
  expect(reorderJson.data.kbs[0]?.kb_id).toBe("kb_e2e");

  const rebuild = await request.post(`${state.backendUrl}/api/projects/${projectId}/vector/rebuild`, {
    data: { kb_ids: ["default", "kb_e2e"], sources: ["worldbook"] },
  });
  expect(rebuild.ok()).toBeTruthy();
  const rebuildJson = (await rebuild.json()) as ApiOk<{ result: { enabled: boolean; skipped: boolean } }>;
  expect(rebuildJson.ok).toBe(true);
  expect(rebuildJson.data.result.enabled).toBe(true);
  expect(Boolean(rebuildJson.data.result.skipped)).toBe(false);

  const query = await request.post(`${state.backendUrl}/api/projects/${projectId}/vector/query`, {
    data: { kb_ids: ["default", "kb_e2e"], query_text: "dragon", sources: ["worldbook"] },
  });
  expect(query.ok()).toBeTruthy();
  const queryJson = (await query.json()) as ApiOk<{ result: { enabled: boolean; kbs?: unknown } }>;
  expect(queryJson.ok).toBe(true);
  expect(queryJson.data.result.enabled).toBe(true);

  const raw = JSON.stringify(queryJson);
  expect(raw).toContain('"kbs"');
  expect(raw).toContain('"per_kb"');
  expect(raw).toContain('"kb_e2e"');
  expect(raw).toContain('"default"');

  // Must not leak api keys or secrets.
  expect(raw).not.toContain("test-key");
  expect(raw).not.toMatch(/sk-[a-zA-Z0-9]{10,}/);

  const disable = await request.put(`${state.backendUrl}/api/projects/${projectId}/vector/kbs/kb_e2e`, {
    data: { enabled: false },
  });
  expect(disable.ok()).toBeTruthy();

  const del = await request.delete(`${state.backendUrl}/api/projects/${projectId}/vector/kbs/kb_e2e`);
  expect(del.ok()).toBeTruthy();

  const list2 = await request.get(`${state.backendUrl}/api/projects/${projectId}/vector/kbs`);
  expect(list2.ok()).toBeTruthy();
  const list2Json = (await list2.json()) as ApiOk<{ kbs: Array<{ kb_id: string }> }>;
  expect(list2Json.ok).toBe(true);
  expect(list2Json.data.kbs.some((k) => k.kb_id === "kb_e2e")).toBe(false);
});

