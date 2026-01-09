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
  await expect(dialog.getByText("世界书注入已关闭。开启后可查看触发条目与 text_md。")).toBeVisible();

  await toggle.check();

  await expect(dialog.getByText("世界书（WorldBook）", { exact: true })).toBeVisible();
  await expect(dialog.getByText("keyword:dragon | priority:important", { exact: true })).toBeVisible();
  await expect(dialog.getByText("constant | priority:important", { exact: true })).toBeVisible();

  const textSummary = dialog.locator("summary", { hasText: "text_md（最终注入文本）" });
  await textSummary.click();
  const textDetails = textSummary.locator("..");
  await expect(textDetails).toHaveAttribute("open", "");
  await expect(textDetails).toContainText("<WORLD_BOOK>");
  await expect(dialog.getByRole("button", { name: "关闭", exact: true })).toBeVisible();
});
