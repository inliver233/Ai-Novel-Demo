import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("api: embedding provider fail-soft + masked keys (sentence-transformers missing)", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const rawKey = `e2e-embedding-key-${Date.now()}-SECRET`;

  const put = await request.put(`${state.backendUrl}/api/projects/${projectId}/settings`, {
    data: {
      query_preprocessing: {
        enabled: true,
        tags: ["tag"],
        exclusion_rules: ["EXCLUDE_ME"],
        index_ref_enhance: true,
      },
      vector_embedding_provider: "sentence_transformers",
      vector_embedding_sentence_transformers_model: "all-MiniLM-L6-v2",
      vector_embedding_api_key: rawKey,
    },
  });
  expect(put.ok()).toBeTruthy();

  const get = await request.get(`${state.backendUrl}/api/projects/${projectId}/settings`);
  expect(get.ok()).toBeTruthy();
  const settingsJson = (await get.json()) as ApiOk<{ settings: Record<string, unknown> }>;
  expect(settingsJson.ok).toBe(true);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const settings = settingsJson.data.settings as any;
  expect(settings.query_preprocessing_effective_source).toBe("project");
  expect(settings.query_preprocessing_effective).toMatchObject({
    enabled: true,
    tags: ["tag"],
    exclusion_rules: ["EXCLUDE_ME"],
    index_ref_enhance: true,
  });
  expect(settings.vector_embedding_has_api_key).toBe(true);
  expect(typeof settings.vector_embedding_masked_api_key).toBe("string");
  expect(String(settings.vector_embedding_masked_api_key)).not.toContain(rawKey);

  const disabled = settings.vector_embedding_effective_disabled_reason as string | null | undefined;
  if (disabled !== "dependency_missing") {
    test.skip(true, `sentence-transformers dependency is available (disabled_reason=${String(disabled)})`);
  }

  const status = await request.post(`${state.backendUrl}/api/projects/${projectId}/vector/status`, {
    data: { sources: ["worldbook"] },
  });
  expect(status.ok()).toBeTruthy();
  const statusJson = (await status.json()) as ApiOk<{ result: Record<string, unknown> }>;
  expect(statusJson.ok).toBe(true);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const statusResult = statusJson.data.result as any;
  expect(statusResult.enabled).toBe(false);
  expect(statusResult.disabled_reason).toBe("dependency_missing");

  const query = await request.post(`${state.backendUrl}/api/projects/${projectId}/vector/query`, {
    data: { query_text: "#tag 第12章 EXCLUDE_ME", sources: ["worldbook"] },
  });
  expect(query.ok()).toBeTruthy();
  const queryJson = (await query.json()) as ApiOk<{
    result: Record<string, unknown>;
    raw_query_text: string;
    normalized_query_text: string;
    preprocess_obs: Record<string, unknown>;
  }>;
  expect(queryJson.ok).toBe(true);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const queryResult = queryJson.data.result as any;
  expect(queryResult.enabled).toBe(false);
  expect(queryResult.disabled_reason).toBe("dependency_missing");
  expect(Array.isArray(queryResult.candidates)).toBe(true);
  expect(queryResult.candidates.length).toBe(0);
  expect(queryJson.data.normalized_query_text).toContain("chapter:12");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  expect((queryJson.data.preprocess_obs as any).enabled).toBe(true);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  expect(((queryJson.data.preprocess_obs as any).extracted_tags ?? [])).toContain("tag");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  expect(((queryJson.data.preprocess_obs as any).applied_exclusion_rules ?? [])).toContain("EXCLUDE_ME");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  expect(((queryJson.data.preprocess_obs as any).index_refs ?? [])).toContain("chapter:12");

  const mem = await request.get(`${state.backendUrl}/api/projects/${projectId}/memory/retrieve`);
  expect(mem.ok()).toBeTruthy();
  const memJson = (await mem.json()) as ApiOk<{ vector_rag: Record<string, unknown> }>;
  expect(memJson.ok).toBe(true);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  expect((memJson.data as any).vector_rag.disabled_reason).toBe("dependency_missing");

  // Must not leak API keys in any response payload.
  const raw = JSON.stringify({ settingsJson, statusJson, queryJson, memJson });
  expect(raw).not.toContain(rawKey);
  expect(raw).not.toMatch(/sk-[a-zA-Z0-9]{10,}/);
});
