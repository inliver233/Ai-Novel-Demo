import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: chapter analyze -> apply -> ChapterAnalysisPage highlights + sidebar", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "要点 A；要点 B" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as { ok: boolean; data: { chapter: { id: string } } };
  const chapterId = createJson.data.chapter.id;

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);

  const content = page.locator('textarea[name="content_md"]');
  await content.fill("E2E 原始正文…用于章节分析与落库。");

  await page.getByRole("button", { name: "分析", exact: true }).click();
  const modal = page.getByRole("dialog", { name: "章节分析" });
  await expect(modal).toBeVisible();

  await modal.getByRole("button", { name: "开始分析", exact: true }).click();
  await expect(modal.getByText("本章摘要", { exact: true })).toBeVisible({ timeout: 60_000 });

  await modal.getByRole("button", { name: "保存到记忆库", exact: true }).click();
  await expect(page.getByText(/已生成 \d+ 条记忆/)).toBeVisible({ timeout: 60_000 });

  await page.getByRole("button", { name: "打开标注页", exact: true }).click();

  await expect(page.getByText("章节标注回溯", { exact: true })).toBeVisible();
  await expect(page.getByText("记忆侧栏", { exact: true })).toBeVisible();

  const highlights = page.locator("[data-annotation-id]");
  await expect.poll(async () => await highlights.count(), { timeout: 60_000 }).toBeGreaterThan(0);
});
