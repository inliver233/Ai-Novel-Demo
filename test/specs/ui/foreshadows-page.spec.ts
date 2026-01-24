import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: foreshadows page open loops -> search -> resolve -> refresh", async ({ page, request }) => {
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
  await content.fill("E2E 原始正文…用于伏笔时间线页回归。");

  await page.getByRole("button", { name: "分析", exact: true }).click();
  const modal = page.getByRole("dialog", { name: "章节分析", exact: true });
  await expect(modal).toBeVisible();

  await modal.getByRole("button", { name: "开始分析", exact: true }).click();
  await expect(modal.getByText("本章摘要", { exact: true })).toBeVisible({ timeout: 60_000 });

  await modal.getByRole("button", { name: "保存到记忆库", exact: true }).click();
  await expect(page.getByText(/已生成 \d+ 条记忆/)).toBeVisible({ timeout: 60_000 });

  await page.goto(`/projects/${projectId}/foreshadows?chapterId=${chapterId}`);
  await expect(page.getByText("伏笔时间线", { exact: true })).toBeVisible();

  const resolveBtns = page.getByRole("button", { name: "标记回收", exact: true });
  await expect.poll(async () => await resolveBtns.count(), { timeout: 60_000 }).toBeGreaterThan(0);

  const qInput = page.getByLabel("foreshadows_query", { exact: true });
  await qInput.fill("zzzz-not-found");
  await page.getByRole("button", { name: "应用", exact: true }).click();
  await expect(page.getByText("暂无未回收伏笔。", { exact: true })).toBeVisible({ timeout: 60_000 });

  await page.getByRole("button", { name: "清空", exact: true }).click();
  await expect.poll(async () => await resolveBtns.count(), { timeout: 60_000 }).toBeGreaterThan(0);

  const chapterSelect = page.getByLabel("foreshadows_resolve_chapter_id", { exact: true });
  await expect(chapterSelect).toBeEnabled({ timeout: 60_000 });
  await chapterSelect.selectOption({ value: chapterId });

  const before = await resolveBtns.count();
  await resolveBtns.first().click();
  const confirm = page.getByRole("dialog", { name: "标记伏笔已回收？", exact: true });
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", { name: "标记回收", exact: true }).click();
  await expect.poll(async () => await resolveBtns.count(), { timeout: 60_000 }).toBe(before - 1);

  await page.getByRole("button", { name: "刷新", exact: true }).click();
  await expect.poll(async () => await resolveBtns.count(), { timeout: 60_000 }).toBe(before - 1);
});

