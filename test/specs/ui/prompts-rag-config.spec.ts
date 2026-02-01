import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("ui: prompts can save vector rag config", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  await page.goto(`/projects/${projectId}/prompts#rag-config`);
  await expect(page.getByRole("heading", { name: "模型配置", exact: true })).toBeVisible();

  const ragRegion = page.getByRole("region", { name: "向量检索（Vector RAG）", exact: true });
  await expect(ragRegion).toBeVisible();

  await ragRegion.getByText("Embedding（向量化）配置", { exact: true }).click();

  await ragRegion.locator('select[name="vector_embedding_provider"]').selectOption("openai_compatible");
  await ragRegion.locator('input[name="vector_embedding_base_url"]').fill(state.mockLlmBaseUrl);
  await ragRegion.locator('input[name="vector_embedding_model"]').fill("text-embedding-3-small");
  await ragRegion.locator('input[name="vector_embedding_api_key"]').fill("vector-test-key");

  await ragRegion.locator('input[name="vector_rerank_enabled"]').check();
  await ragRegion.locator('select[name="vector_rerank_method"]').selectOption("token_overlap");
  await ragRegion.locator('input[name="vector_rerank_top_k"]').fill("12");
  await ragRegion.locator('input[name="vector_rerank_top_k"]').blur();

  await ragRegion.getByText("Rerank 提供方配置", { exact: true }).click();
  await ragRegion.locator('select[name="vector_rerank_provider"]').selectOption("external_rerank_api");
  await ragRegion.locator('input[name="vector_rerank_base_url"]').fill(state.mockLlmBaseUrl);
  await ragRegion.locator('input[name="vector_rerank_model"]').fill("rerank-model-1");
  await ragRegion.locator('input[name="vector_rerank_timeout_seconds"]').fill("13");
  await ragRegion.locator('input[name="vector_rerank_timeout_seconds"]').blur();
  await ragRegion.locator('input[name="vector_rerank_hybrid_alpha"]').fill("0.25");
  await ragRegion.locator('input[name="vector_rerank_hybrid_alpha"]').blur();
  await ragRegion.locator('input[name="vector_rerank_api_key"]').fill("rerank-test-key");

  await ragRegion.getByRole("button", { name: "保存 RAG 配置", exact: true }).click();
  await expect(page.getByText("已保存", { exact: true })).toBeVisible();

  const settingsRes = await request.get(`${state.backendUrl}/api/projects/${projectId}/settings`);
  expect(settingsRes.ok()).toBeTruthy();
  const settingsJson = (await settingsRes.json()) as ApiOk<{ settings: Record<string, unknown> }>;

  const settings = settingsJson.data.settings as {
    vector_embedding_provider: string;
    vector_embedding_base_url: string;
    vector_embedding_model: string;
    vector_embedding_has_api_key: boolean;
    vector_embedding_masked_api_key: string;
    vector_rerank_provider: string;
    vector_rerank_base_url: string;
    vector_rerank_model: string;
    vector_rerank_timeout_seconds: number | null;
    vector_rerank_hybrid_alpha: number | null;
    vector_rerank_has_api_key: boolean;
    vector_rerank_masked_api_key: string;
    vector_rerank_effective_enabled: boolean;
    vector_rerank_effective_method: string;
    vector_rerank_effective_top_k: number;
  };

  expect(settings.vector_embedding_provider).toBe("openai_compatible");
  expect(settings.vector_embedding_base_url).toBe(state.mockLlmBaseUrl);
  expect(settings.vector_embedding_model).toBe("text-embedding-3-small");
  expect(settings.vector_embedding_has_api_key).toBe(true);
  expect(settings.vector_embedding_masked_api_key).toBeTruthy();
  expect(settings.vector_embedding_masked_api_key).not.toBe("vector-test-key");

  expect(settings.vector_rerank_provider).toBe("external_rerank_api");
  expect(settings.vector_rerank_base_url).toBe(state.mockLlmBaseUrl);
  expect(settings.vector_rerank_model).toBe("rerank-model-1");
  expect(settings.vector_rerank_timeout_seconds).toBe(13);
  expect(settings.vector_rerank_hybrid_alpha).toBe(0.25);
  expect(settings.vector_rerank_has_api_key).toBe(true);
  expect(settings.vector_rerank_masked_api_key).toBeTruthy();
  expect(settings.vector_rerank_masked_api_key).not.toBe("rerank-test-key");

  expect(settings.vector_rerank_effective_enabled).toBe(true);
  expect(settings.vector_rerank_effective_method).toBe("token_overlap");
  expect(settings.vector_rerank_effective_top_k).toBe(12);

  await ragRegion.getByRole("button", { name: "清除项目级 Rerank API Key", exact: true }).click();
  await ragRegion.getByRole("button", { name: "保存 RAG 配置", exact: true }).click();

  const settingsRes2 = await request.get(`${state.backendUrl}/api/projects/${projectId}/settings`);
  expect(settingsRes2.ok()).toBeTruthy();
  const settingsJson2 = (await settingsRes2.json()) as ApiOk<{ settings: Record<string, unknown> }>;
  const settings2 = settingsJson2.data.settings as { vector_rerank_has_api_key: boolean; vector_rerank_masked_api_key: string };
  expect(settings2.vector_rerank_has_api_key).toBe(false);
  expect(settings2.vector_rerank_masked_api_key).toBeFalsy();
});
