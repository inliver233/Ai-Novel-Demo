import { test, expect } from "../../lib/ui-test";

import type { APIRequestContext } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

async function seedWorldbookForInjection(request: APIRequestContext, projectId: string): Promise<void> {
  const state = loadState();

  const constantRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries`, {
    data: {
      title: "E2E WB Constant",
      content_md: "dragon",
      enabled: true,
      constant: true,
      keywords: [],
      exclude_recursion: false,
      prevent_recursion: false,
      char_limit: 12000,
      priority: "important",
    },
  });
  if (!constantRes.ok()) throw new Error(`Failed to create constant entry: ${constantRes.status()} ${await constantRes.text()}`);

  const keywordRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries`, {
    data: {
      title: "E2E WB Keyword",
      content_md: "E2E_KEYWORD_CONTENT",
      enabled: true,
      constant: false,
      keywords: ["dragon"],
      exclude_recursion: false,
      prevent_recursion: false,
      char_limit: 12000,
      priority: "important",
    },
  });
  if (!keywordRes.ok()) throw new Error(`Failed to create keyword entry: ${keywordRes.status()} ${await keywordRes.text()}`);
  const keywordJson = (await keywordRes.json()) as ApiOk<{ worldbook_entry: { id: string } }>;
  if (!keywordJson.ok) throw new Error("Keyword entry response not ok");
}

test("ui: writing ContextPreviewDrawer supports worldbook injection toggle", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);
  await seedWorldbookForInjection(request, projectId);

  await page.goto(`/projects/${projectId}/writing`);
  await expect(page.getByRole("button", { name: "上下文预览", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "上下文预览", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "上下文预览" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("MemoryContextPack / logs")).toBeVisible();

  const toggle = dialog.getByRole("checkbox", { name: "世界书注入", exact: true });
  await expect(toggle).toBeVisible();
  await expect(toggle).toBeChecked();

  // Advanced users can still disable it.
  await toggle.uncheck();
  await expect(dialog.getByText("世界书注入已关闭。开启后可查看触发条目与 text_md。", { exact: true })).toBeVisible();
  await toggle.check();

  const packSummary = dialog.locator("summary", { hasText: "Pack sections" });
  await packSummary.click();
  const packDetails = packSummary.locator("..");
  await expect(packDetails).toHaveAttribute("open", "");
  const storyMemoryCard = dialog.getByText("story_memory", { exact: true }).locator("..").locator("..");
  await expect(storyMemoryCard).toContainText("disabled: empty");
  await expect(dialog.getByText("semantic_history", { exact: true })).toBeVisible();
  await expect(dialog.getByText("foreshadow_open_loops", { exact: true })).toBeVisible();
  await expect(dialog.getByText("vector_rag", { exact: true })).toBeVisible();

  await expect(dialog.getByText("世界书（WorldBook）", { exact: true })).toBeVisible();
  const triggeredSummary = dialog.locator("summary", { hasText: "触发条目" });
  await triggeredSummary.click();
  const triggeredDetails = triggeredSummary.locator("..");
  await expect(triggeredDetails).toHaveAttribute("open", "");
  await expect(dialog.getByText("keyword:dragon | priority:important", { exact: true })).toBeVisible();
  await expect(dialog.getByText("constant | priority:important", { exact: true })).toBeVisible();

  const textSummary = dialog.locator("summary", { hasText: /^text_md（最终注入文本）$/ });
  await textSummary.click();
  const textDetails = textSummary.locator("..");
  await expect(textDetails).toHaveAttribute("open", "");
  await expect(textDetails).toContainText("<WORLD_BOOK>");
  await expect(dialog.getByRole("button", { name: "关闭", exact: true })).toBeVisible();
});

test("ui: writing ContextPreviewDrawer supports Vector RAG debug query preview", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  await page.goto(`/projects/${projectId}/writing`);
  await page.getByRole("button", { name: "上下文预览", exact: true }).click();

  const dialog = page.getByRole("dialog", { name: "上下文预览" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Vector RAG 调试", { exact: true })).toBeVisible();

  const queryInput = dialog.getByLabel("query_text", { exact: true });
  await expect(queryInput).toBeVisible();
  await queryInput.fill("dragon");

  await dialog.getByRole("button", { name: "查询", exact: true }).click();

  await expect(dialog.getByText(/counts:/)).toBeVisible();
  await expect(dialog.getByText("注入预览（prompt_block.text_md）", { exact: true })).toBeVisible();

  const rawSummary = dialog.locator("summary", { hasText: "raw vector query result" });
  await rawSummary.click();
  const rawDetails = rawSummary.locator("..");
  await expect(rawDetails).toHaveAttribute("open", "");
  await expect(rawDetails).toContainText('"query_text": "dragon"');
});
