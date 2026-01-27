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

test("ui: writing ContextPreviewDrawer syncs preview params from AI generate drawer", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);
  await seedWorldbookForInjection(request, projectId);

  await page.goto(`/projects/${projectId}/writing`);

  await expect(page.getByRole("button", { name: "新增章节" })).toBeVisible();
  await page.getByRole("button", { name: "新增章节" }).click();
  await expect(page.getByRole("dialog", { name: "新增章节" })).toBeVisible();
  await page.locator('input[name="number"]').fill("1");
  await page.locator('input[name="title"]').fill("E2E 第一章");
  await page.locator('textarea[name="plan"]').fill("dragon");
  await page.getByRole("button", { name: "创建", exact: true }).click();
  await expect(page.getByRole("button", { name: "AI 生成" })).toBeVisible();

  await page.getByRole("button", { name: "AI 生成", exact: true }).click();
  const genDrawer = page.getByRole("dialog", { name: "AI 生成", exact: true });
  await expect(genDrawer).toBeVisible();

  await genDrawer.getByRole("checkbox", { name: "世界书注入", exact: true }).check();
  await genDrawer.getByRole("checkbox", { name: "世界书（worldbook）", exact: true }).check();
  await genDrawer.getByLabel("memory_query_text", { exact: true }).fill("dragon");
  await genDrawer.getByRole("button", { name: "关闭", exact: true }).click();
  await expect(genDrawer).not.toBeVisible();

  await page.getByRole("button", { name: "上下文预览", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "上下文预览", exact: true });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("checkbox", { name: "世界书注入", exact: true })).toBeChecked();

  const previewQuery = dialog.locator('textarea[name="memory_preview_query_text"]');
  await expect(previewQuery).toHaveValue("dragon");

  const packSummary = dialog.locator("summary", { hasText: "Pack sections" });
  await packSummary.click();
  const packPanel = packSummary.locator("..");
  await expect(packPanel).toHaveAttribute("open", "");

  const worldbookModule = dialog.getByRole("checkbox", { name: "世界书（worldbook）", exact: true });
  await worldbookModule.uncheck();
  await dialog.getByRole("button", { name: "刷新", exact: true }).click();

  const worldbookCard = packPanel.getByText("worldbook", { exact: true }).locator("..").locator("..");
  await expect(worldbookCard).toContainText("disabled: disabled");
  const triggeredSummary = dialog.locator("summary", { hasText: "触发条目" });
  await triggeredSummary.click();
  const triggeredDetails = triggeredSummary.locator("..");
  await expect(triggeredDetails).toHaveAttribute("open", "");
  await expect(dialog.getByText("未触发任何条目", { exact: true })).toBeVisible();

  await dialog.getByRole("button", { name: "同步生成设置", exact: true }).click();
  await expect(worldbookModule).toBeChecked();
  await expect(previewQuery).toHaveValue("dragon");
  await expect(worldbookCard).toContainText("enabled");
  await expect(dialog.getByText("keyword:dragon | priority:important", { exact: true })).toBeVisible();
  await expect(dialog.getByText("constant | priority:important", { exact: true })).toBeVisible();
});
