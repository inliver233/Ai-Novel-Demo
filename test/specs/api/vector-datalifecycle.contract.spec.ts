import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("api: vector dirty -> rebuild clears -> purge empties", async ({ request }) => {
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

  const createRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries`, {
    data: {
      title: "E2E WB Vector Dirty",
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
  expect(createRes.ok()).toBeTruthy();

  const status1 = await request.post(`${state.backendUrl}/api/projects/${projectId}/vector/status`, {
    data: { sources: ["worldbook"] },
  });
  expect(status1.ok()).toBeTruthy();
  const status1Json = (await status1.json()) as ApiOk<{ result: { index: { dirty: boolean; last_build_at: string | null } } }>;
  expect(status1Json.ok).toBe(true);
  // In E2E, dev uses an inline background worker; vector rebuild may complete quickly after worldbook writes.
  // Contract: index must either be marked dirty (needs rebuild) OR already have a last_build_at timestamp.
  if (!status1Json.data.result.index.dirty) {
    expect(typeof status1Json.data.result.index.last_build_at).toBe("string");
  }

  const rebuild = await request.post(`${state.backendUrl}/api/projects/${projectId}/vector/rebuild`, {
    data: { sources: ["worldbook"] },
  });
  expect(rebuild.ok()).toBeTruthy();
  const rebuildJson = (await rebuild.json()) as ApiOk<{ result: { enabled: boolean; skipped?: boolean } }>;
  expect(rebuildJson.ok).toBe(true);
  expect(rebuildJson.data.result.enabled).toBe(true);
  expect(Boolean(rebuildJson.data.result.skipped)).toBe(false);

  const status2 = await request.post(`${state.backendUrl}/api/projects/${projectId}/vector/status`, {
    data: { sources: ["worldbook"] },
  });
  expect(status2.ok()).toBeTruthy();
  const status2Json = (await status2.json()) as ApiOk<{ result: { index: { dirty: boolean; last_build_at: string | null } } }>;
  expect(status2Json.ok).toBe(true);
  expect(status2Json.data.result.index.dirty).toBe(false);
  expect(typeof status2Json.data.result.index.last_build_at).toBe("string");

  const query1 = await request.post(`${state.backendUrl}/api/projects/${projectId}/vector/query`, {
    data: { query_text: "dragon", sources: ["worldbook"] },
  });
  expect(query1.ok()).toBeTruthy();
  const query1Json = (await query1.json()) as ApiOk<{ result: { candidates: unknown[] } }>;
  expect(query1Json.ok).toBe(true);
  expect(Array.isArray(query1Json.data.result.candidates)).toBe(true);
  expect(query1Json.data.result.candidates.length).toBeGreaterThan(0);

  const purge = await request.post(`${state.backendUrl}/api/projects/${projectId}/vector/purge`);
  expect(purge.ok()).toBeTruthy();
  const purgeJson = (await purge.json()) as ApiOk<{ result: { deleted: boolean } }>;
  expect(purgeJson.ok).toBe(true);
  expect(purgeJson.data.result.deleted).toBe(true);

  const query2 = await request.post(`${state.backendUrl}/api/projects/${projectId}/vector/query`, {
    data: { query_text: "dragon", sources: ["worldbook"] },
  });
  expect(query2.ok()).toBeTruthy();
  const query2Json = (await query2.json()) as ApiOk<{ result: { candidates: unknown[] } }>;
  expect(query2Json.ok).toBe(true);
  expect(Array.isArray(query2Json.data.result.candidates)).toBe(true);
  expect(query2Json.data.result.candidates.length).toBe(0);

  // Must not leak api keys or secrets (bootstrapProject uses "test-key").
  const raw = JSON.stringify({ rebuildJson, status2Json, purgeJson, query2Json });
  expect(raw).not.toContain("test-key");
  expect(raw).not.toMatch(/sk-[a-zA-Z0-9]{10,}/);
});
