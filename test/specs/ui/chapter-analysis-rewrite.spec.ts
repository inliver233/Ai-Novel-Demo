import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: chapter analyze -> rewrite -> apply to editor", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "要点 A；要点 B" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as { ok: boolean; data: { chapter: { id: string } } };
  const chapterId = createJson.data.chapter.id;

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);
  await expect(page.getByRole("button", { name: "分析", exact: true })).toBeVisible();

  const content = page.locator('textarea[name="content_md"]');
  await content.fill("E2E 原始正文：用于章节分析与重写。");

  await page.getByRole("button", { name: "分析", exact: true }).click();
  const modal = page.getByRole("dialog", { name: "章节分析" });
  await expect(modal).toBeVisible();

  await modal.getByRole("button", { name: "开始分析", exact: true }).click();
  await expect(modal.getByText("本章摘要")).toBeVisible({ timeout: 60_000 });
  await expect(modal.getByText("这是章节分析摘要（E2E）", { exact: true })).toBeVisible();

  await modal.getByRole("button", { name: "按建议重写并应用", exact: true }).click();
  await expect(content).toContainText("重写后的正文", { timeout: 60_000 });
});
