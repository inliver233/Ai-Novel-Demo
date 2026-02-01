import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: worldbook auto_update is fail-soft + retryable", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "用于 worldbook auto_update", status: "drafting" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as { ok: boolean; data: { chapter: { id: string } } };
  const chapterId = createJson.data.chapter.id;

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);
  await expect(page.getByRole("textbox", { name: "标题", exact: true })).toHaveValue("E2E 第一章", { timeout: 60_000 });

  // Mark the chapter as done and save. This should enqueue worldbook_auto_update as a ProjectTask.
  await page.getByRole("combobox", { name: /^状态/ }).selectOption("done");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByRole("button", { name: "保存", exact: true })).toBeDisabled({ timeout: 60_000 });

  // Fail-soft: even if worldbook_auto_update fails, writing page remains usable.
  await expect(page.getByText("正文（Markdown）", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "分析", exact: true })).toBeVisible();

  // Navigate to TaskCenter and verify task visibility + retry.
  await page.getByRole("button", { name: "任务中心", exact: true }).click();
  const projectTasksPanel = page.getByRole("region", { name: "项目任务 (taskcenter_projecttasks_section)", exact: true });
  await expect(projectTasksPanel).toBeVisible({ timeout: 60_000 });

  await projectTasksPanel
    .getByRole("button", { name: "项目任务仅看失败 (taskcenter_projecttask_failed_only)", exact: true })
    .click();

  const worldbookTask = projectTasksPanel.locator("button.surface").filter({ hasText: "worldbook_auto_update" }).first();
  await expect(worldbookTask).toBeVisible({ timeout: 60_000 });
  await expect(worldbookTask).toContainText("（failed）");

  await worldbookTask.getByRole("button", { name: "项目任务重试 (taskcenter_projecttask_retry)", exact: true }).click();

  // Under mock-llm, retry likely fails again, but it must remain retryable and observable.
  await expect
    .poll(async () => await projectTasksPanel.locator("button.surface").filter({ hasText: "worldbook_auto_update" }).count(), {
      timeout: 60_000,
    })
    .toBeGreaterThan(0);
});
