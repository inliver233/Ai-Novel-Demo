import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("api: vector query supports multi-chunk per source_id (chapter) + chunk_index", async ({ request }) => {
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

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E Long Chapter", plan: "" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as ApiOk<{ chapter: { id: string } }>;
  const chapterId = createJson.data.chapter.id;

  const longContent = Array.from({ length: 120 }, (_, i) => `段落 ${i}: dragon dragon dragon dragon dragon`).join("\n\n");
  const update = await request.put(`${state.backendUrl}/api/chapters/${chapterId}`, {
    data: { content_md: longContent, status: "done" },
  });
  expect(update.ok()).toBeTruthy();

  const rebuild = await request.post(`${state.backendUrl}/api/projects/${projectId}/vector/rebuild`, {
    data: { sources: ["chapter"] },
  });
  expect(rebuild.ok()).toBeTruthy();
  const rebuildJson = (await rebuild.json()) as ApiOk<{ result: { enabled: boolean; skipped: boolean; disabled_reason?: string } }>;
  expect(rebuildJson.data.result.enabled).toBe(true);
  expect(Boolean(rebuildJson.data.result.skipped)).toBe(false);

  const query = await request.post(`${state.backendUrl}/api/projects/${projectId}/vector/query`, {
    data: { query_text: "dragon", sources: ["chapter"] },
  });
  expect(query.ok()).toBeTruthy();
  const queryJson = (await query.json()) as ApiOk<{ result: Record<string, unknown> }>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const result = queryJson.data.result as any;

  expect(result.enabled).toBe(true);
  expect(Array.isArray(result.final?.chunks)).toBe(true);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const chunks = (result.final?.chunks ?? []) as any[];
  expect(chunks.length).toBeGreaterThan(1);

  const sourceIds = chunks.map((c) => String(c?.metadata?.source_id ?? ""));
  const uniqueSourceIds = new Set(sourceIds.filter(Boolean));
  expect(uniqueSourceIds.size).toBe(1);

  const indices = chunks.map((c) => Number(c?.metadata?.chunk_index));
  expect(indices.every((n) => Number.isFinite(n))).toBe(true);
  const uniqueIndices = new Set(indices.map((n) => String(n)));
  expect(uniqueIndices.size).toBeGreaterThan(1);

  // With VECTOR_PER_SOURCE_ID_MAX_CHUNKS enabled in E2E setup, extra chunks should be dropped.
  const dropped = Array.isArray(result.dropped) ? result.dropped : [];
  const hasPerSourceBudget = dropped.some((d) => d && typeof d === "object" && (d as { reason?: string }).reason === "per_source_budget");
  expect(hasPerSourceBudget).toBe(true);
});
