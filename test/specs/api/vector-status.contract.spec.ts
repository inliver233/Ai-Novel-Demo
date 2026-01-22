import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("api: vector/status returns stable result shape incl index + rerank", async ({ request }) => {
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
      title: "E2E Vector Status",
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

  const status = await request.post(`${state.backendUrl}/api/projects/${projectId}/vector/status`, {
    data: { sources: ["worldbook"] },
  });
  expect(status.ok()).toBeTruthy();

  const statusJson = (await status.json()) as ApiOk<{ result: Record<string, unknown> }>;
  expect(statusJson.ok).toBe(true);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const result = statusJson.data.result as any;
  expect(typeof result.enabled).toBe("boolean");
  expect(result.disabled_reason === null || typeof result.disabled_reason === "string").toBeTruthy();
  expect(typeof result.filters?.project_id).toBe("string");
  expect(Array.isArray(result.filters?.sources)).toBe(true);
  expect(typeof result.index?.dirty).toBe("boolean");
  expect(result.index?.last_build_at === null || typeof result.index?.last_build_at === "string").toBeTruthy();
  expect(typeof result.backend_preferred).toBe("string");
  expect(typeof result.hybrid_enabled).toBe("boolean");
  expect(typeof result.rerank).toBe("object");
  expect(typeof result.final?.text_md).toBe("string");
  expect(Array.isArray(result.final?.chunks)).toBe(true);
  expect(typeof result.final?.truncated).toBe("boolean");

  // Must not leak api keys or secrets.
  const raw = JSON.stringify(statusJson);
  expect(raw).not.toContain("test-key");
  expect(raw).not.toMatch(/sk-[a-zA-Z0-9]{10,}/);
});

