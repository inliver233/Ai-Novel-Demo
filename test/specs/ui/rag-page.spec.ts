import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: rag page supports status + query injection preview", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  await page.goto(`/projects/${projectId}/rag`);
  await expect(page.getByText("Vector RAG 管理", { exact: true })).toBeVisible();

  await page.getByLabel("刷新状态 (rag_refresh_status)", { exact: true }).click();
  await expect(page.getByText(/disabled_reason:/)).toBeVisible();

  const queryInput = page.getByLabel("query_text", { exact: true });
  await queryInput.fill("dragon");
  await page.getByLabel("查询 (rag_query)", { exact: true }).click();

  await expect(page.locator("summary", { hasText: /^注入预览/ })).toBeVisible();

  const rawDetails = page
    .locator("details", { hasText: '"query_text": "dragon"' })
    .filter({ hasText: '"final"' })
    .first();
  await rawDetails.locator("summary").click();
  await expect(rawDetails).toHaveAttribute("open", "");
  await expect(rawDetails).toContainText('"query_text": "dragon"');
});

test("ui: rag page supports KB manage + multi-kb rebuild/query", async ({ page, request }) => {
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
      title: "E2E WB KB",
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

  await page.goto(`/projects/${projectId}/rag`);
  await expect(page.getByRole("region", { name: "知识库 (rag_kb_section)", exact: true })).toBeVisible();

  await page.getByLabel("kb_create_name", { exact: true }).fill(`E2E_KB_${Date.now()}`);
  await page.getByLabel("创建 KB (rag_kb_create)", { exact: true }).click();

  const newKbIdEl = page.getByText(/^kb_/, { exact: false }).first();
  await expect(newKbIdEl).toBeVisible();
  const newKbId = (await newKbIdEl.textContent())?.trim() || "";
  expect(newKbId).toMatch(/^kb_/);

  await page.locator(`input[aria-label="选择 KB ${newKbId}"]`).check();
  await page.locator(`input[aria-label="选择 KB default"]`).check();

  await page.locator(`input[aria-label="KB 权重 ${newKbId}"]`).fill("3");
  await page.getByLabel(`保存 KB ${newKbId}`, { exact: true }).click();

  await page.getByLabel(/rag_rebuild/).click();
  const debugDetails = page.locator("summary", { hasText: "高级调试" }).locator("..");
  await expect(debugDetails).toHaveAttribute("open", "");
  await expect(page.getByText(/^重建结果/)).toBeVisible();

  await page.getByLabel("query_text", { exact: true }).fill("dragon");
  await page.getByLabel("查询 (rag_query)", { exact: true }).click();

  const rawDetails = page
    .locator("details", { hasText: '"query_text": "dragon"' })
    .filter({ hasText: '"final"' })
    .first();
  await rawDetails.locator("summary").click();
  await expect(rawDetails).toHaveAttribute("open", "");
  await expect(rawDetails).toContainText(newKbId);
  await expect(rawDetails).toContainText('"kbs"');
});

test("ui: rag page displays grouped multi-chunk final.chunks for chapters", async ({ page, request }) => {
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
  const createJson = (await create.json()) as { ok: boolean; data: { chapter: { id: string } } };
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

  await page.goto(`/projects/${projectId}/rag`);
  await expect(page.getByText("Vector RAG 管理", { exact: true })).toBeVisible();

  await page.getByLabel("query_text", { exact: true }).fill("dragon");
  await page.getByLabel("查询 (rag_query)", { exact: true }).click();

  const chunkTextBlocks = page.locator("details.bg-surface.p-2 pre.whitespace-pre-wrap");
  await expect.poll(async () => await chunkTextBlocks.count(), { timeout: 30_000 }).toBeGreaterThan(1);
});
