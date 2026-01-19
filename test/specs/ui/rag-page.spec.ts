import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: rag page supports status + query injection preview", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  await page.goto(`/projects/${projectId}/rag`);
  await expect(page.getByText("Vector RAG 管理", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "刷新状态", exact: true }).click();
  await expect(page.getByText(/disabled_reason:/)).toBeVisible();

  const queryInput = page.getByLabel("query_text", { exact: true });
  await queryInput.fill("dragon");
  await page.getByRole("button", { name: "查询", exact: true }).click();

  await expect(page.getByText("注入预览（prompt_block.text_md）", { exact: true })).toBeVisible();

  const rawSummary = page.locator("summary", { hasText: "raw vector query result" });
  await rawSummary.click();
  const rawDetails = rawSummary.locator("..");
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
  await expect(page.getByText("Knowledge Bases", { exact: true })).toBeVisible();

  await page.getByLabel("kb_create_name", { exact: true }).fill(`E2E_KB_${Date.now()}`);
  await page.getByRole("button", { name: "创建 KB", exact: true }).click();

  const newKbIdEl = page.getByText(/^kb_/, { exact: false }).first();
  await expect(newKbIdEl).toBeVisible();
  const newKbId = (await newKbIdEl.textContent())?.trim() || "";
  expect(newKbId).toMatch(/^kb_/);

  await page.locator(`input[aria-label="选择 KB ${newKbId}"]`).check();
  await page.locator(`input[aria-label="选择 KB default"]`).check();

  await page.locator(`input[aria-label="KB 权重 ${newKbId}"]`).fill("3");
  await page.getByLabel(`保存 KB ${newKbId}`, { exact: true }).click();

  await page.getByRole("button", { name: /Rebuild/ }).click();
  await expect(page.getByText(/Rebuild result/)).toBeVisible();

  await page.getByLabel("query_text", { exact: true }).fill("dragon");
  await page.getByRole("button", { name: "查询", exact: true }).click();

  const rawSummary = page.locator("summary", { hasText: "raw vector query result" });
  await rawSummary.click();
  const rawDetails = rawSummary.locator("..");
  await expect(rawDetails).toHaveAttribute("open", "");
  await expect(rawDetails).toContainText(newKbId);
  await expect(rawDetails).toContainText('"kbs"');
});
