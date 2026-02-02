import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: writing generate -> save -> trigger auto updates is trackable in TaskCenter", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const createChapterRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 无感更新", plan: "" },
  });
  expect(createChapterRes.ok()).toBeTruthy();
  const createChapterJson = (await createChapterRes.json()) as { ok: boolean; data: { chapter: { id: string } } };
  const chapterId = createChapterJson.data.chapter.id;

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);
  await expect(page.getByRole("textbox", { name: "标题", exact: true })).toHaveValue("E2E 无感更新", { timeout: 60_000 });

  await page.getByRole("button", { name: "AI 生成", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "AI 生成" });
  await expect(drawer).toBeVisible();

  await drawer.getByRole("button", { name: "生成", exact: true }).click();

  const content = page.locator('textarea[name="content_md"]');
  await expect(content).not.toHaveValue("", { timeout: 60_000 });

  await drawer.getByRole("button", { name: "关闭", exact: true }).click();
  await expect(drawer).toBeHidden();

  const saveAndTrigger = page.getByRole("button", { name: "一键保存并触发更新", exact: true });
  await expect(saveAndTrigger).toBeEnabled();
  await saveAndTrigger.click();

  await expect(page.getByText("已保存并创建无感更新任务", { exact: true })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "打开 TaskCenter", exact: true }).click();

  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/tasks`));

  const projectTasksSection = page.getByRole("region", { name: "项目任务 (taskcenter_projecttasks_section)", exact: true });
  await expect(projectTasksSection).toBeVisible({ timeout: 60_000 });

  await expect(projectTasksSection.getByRole("button", { name: /vector_rebuild/ }).first()).toBeVisible({ timeout: 60_000 });
  await expect(projectTasksSection.getByRole("button", { name: /search_rebuild/ }).first()).toBeVisible();
  await expect(projectTasksSection.getByRole("button", { name: /worldbook_auto_update/ }).first()).toBeVisible();
  await expect(projectTasksSection.getByRole("button", { name: /graph_auto_update/ }).first()).toBeVisible();
});
