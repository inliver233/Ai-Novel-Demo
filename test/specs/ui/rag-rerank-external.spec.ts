import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: rag query uses external rerank provider and sends /rerank request", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const mockRoot = state.mockLlmBaseUrl.replace(/\/v1$/, "");
  const resetRes = await request.post(`${mockRoot}/debug/reset`);
  expect(resetRes.ok()).toBeTruthy();

  const probeRes = await request.post(`${state.mockLlmBaseUrl}/embeddings`, {
    data: { model: "text-embedding-mock", input: ["probe"] },
  });
  expect(probeRes.ok()).toBeTruthy();

  const settingsRes = await request.put(`${state.backendUrl}/api/projects/${projectId}/settings`, {
    data: {
      vector_embedding_base_url: state.mockLlmBaseUrl,
      vector_embedding_model: "text-embedding-mock",
      vector_embedding_api_key: "embedding-test-key",

      vector_rerank_enabled: true,
      vector_rerank_method: "auto",
      vector_rerank_top_k: 20,
      vector_rerank_provider: "external_rerank_api",
      vector_rerank_base_url: state.mockLlmBaseUrl,
      vector_rerank_model: "rerank-mock",
      vector_rerank_api_key: "rerank-test-key",
    },
  });
  expect(settingsRes.ok()).toBeTruthy();

  for (const [idx, text] of [
    [1, "E2E DOC A: dragon dragon dragon"],
    [2, "E2E DOC B: dragon dragon"],
    [3, "E2E DOC C: dragon"],
  ] as const) {
    const wbRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries`, {
      data: {
        title: `E2E Rerank Doc ${idx}`,
        content_md: text,
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
  }

  const rebuildRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/vector/rebuild`, {
    data: { sources: ["worldbook"] },
  });
  expect(rebuildRes.ok()).toBeTruthy();

  await page.goto(`/projects/${projectId}/rag`);
  await expect(page.getByText("Vector RAG 管理", { exact: true })).toBeVisible();

  const queryText = "E2E_RERANK_REVERSE dragon";
  await page.getByLabel("query_text", { exact: true }).fill(queryText);
  await page.getByLabel("查询 (rag_query)", { exact: true }).click();

  const rawDetails = page.locator("summary", { hasText: "raw vector query result" }).locator("..");
  await expect(rawDetails).toBeVisible();
  await rawDetails.locator("summary").click();
  await expect(rawDetails).toHaveAttribute("open", "");

  const queryResultText = (await rawDetails.locator("pre").innerText()).trim();
  const queryResult = JSON.parse(queryResultText) as { enabled?: boolean; disabled_reason?: string | null; error?: string | null };
  if (!queryResult.enabled) {
    const statsRes = await request.get(`${mockRoot}/debug/stats`);
    const statsJson = (await statsRes.json()) as {
      ok: true;
      data: {
        embeddings_calls: number;
        last_embeddings: { path: string } | null;
        rerank_calls: number;
        last_rerank: { path: string } | null;
      };
    };
    const errText = String(queryResult.error ?? "").replaceAll("embedding-test-key", "[REDACTED]").replaceAll("rerank-test-key", "[REDACTED]");
    throw new Error(
      `vector/query failed: disabled_reason=${String(queryResult.disabled_reason ?? "-")} error=${errText.slice(0, 220)} ` +
        `| mock.embeddings_calls=${statsJson.data.embeddings_calls} mock.rerank_calls=${statsJson.data.rerank_calls}`,
    );
  }

  const rerankDetails = page.locator("summary", { hasText: "rerank_obs" }).locator("..");
  await expect(rerankDetails).toBeVisible();
  await rerankDetails.locator("summary").click();
  await expect(rerankDetails).toHaveAttribute("open", "");

  const rerankText = (await rerankDetails.locator("pre").innerText()).trim();
  const rerankObs = JSON.parse(rerankText) as {
    enabled?: boolean;
    applied?: boolean;
    method?: string | null;
    provider?: string | null;
    before?: string[];
    after?: string[];
  };

  expect(rerankObs.enabled).toBe(true);
  expect(rerankObs.applied).toBe(true);
  expect(rerankObs.method).toBe("external_rerank_api");
  expect(rerankObs.provider).toBe("external_rerank_api");
  expect(Array.isArray(rerankObs.before)).toBe(true);
  expect(Array.isArray(rerankObs.after)).toBe(true);
  expect(rerankObs.before).not.toEqual(rerankObs.after);

  const statsRes = await request.get(`${mockRoot}/debug/stats`);
  expect(statsRes.ok()).toBeTruthy();
  const statsJson = (await statsRes.json()) as {
    ok: true;
    data: {
      rerank_calls: number;
      last_rerank: {
        path: string;
        query: string | null;
        model: string | null;
        documents_count: number;
        has_api_key: boolean;
      } | null;
    };
  };

  expect(statsJson.data.rerank_calls).toBeGreaterThanOrEqual(1);
  expect(statsJson.data.last_rerank?.path).toMatch(/\/rerank$/);
  expect(statsJson.data.last_rerank?.query).toContain("E2E_RERANK_REVERSE");
  expect(statsJson.data.last_rerank?.documents_count).toBeGreaterThan(1);
  expect(statsJson.data.last_rerank?.has_api_key).toBe(true);
});
