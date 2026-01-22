import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: task center shows change sets + tasks + details", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "用于 TaskCenter", status: "done" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as { ok: boolean; data: { chapter: { id: string } } };
  const chapterId = createJson.data.chapter.id;

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);
  await expect(page.getByRole("textbox", { name: "标题", exact: true })).toHaveValue("E2E 第一章", { timeout: 60_000 });

  // Writing toolbar entry should exist.
  await expect(page.getByRole("button", { name: "任务中心", exact: true })).toBeVisible();

  // Create at least one change_set + task via Memory Update apply.
  await page.getByRole("button", { name: "Memory Update", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "记忆更新（Memory Update）" });
  await expect(dialog).toBeVisible();

  await dialog.getByRole("button", { name: "一键生成提议（Auto Propose）", exact: true }).click();
  await expect(dialog.getByText("步骤 2：审核（Review）", { exact: true })).toBeVisible({ timeout: 60_000 });

  await dialog.getByRole("button", { name: "应用已接受项（Apply）", exact: true }).click();
  await expect(dialog.getByText("应用结果（Apply Result）", { exact: true })).toBeVisible({ timeout: 60_000 });

  // Navigate via MemoryUpdateDrawer entry.
  await dialog.getByRole("button", { name: "任务中心", exact: true }).click();

  const changeSetsPanel = page.getByRole("region", { name: "变更集 (taskcenter_changesets_section)", exact: true });
  const tasksPanel = page.getByRole("region", { name: "任务列表 (taskcenter_tasks_section)", exact: true });
  await expect(changeSetsPanel).toBeVisible({ timeout: 60_000 });
  await expect(tasksPanel).toBeVisible();

  // Wait until list items appear.
  const changeSetItems = changeSetsPanel.locator("button.surface");
  const taskItems = tasksPanel.locator("button.surface");
  await expect.poll(async () => await changeSetItems.count(), { timeout: 60_000 }).toBeGreaterThan(0);
  await expect.poll(async () => await taskItems.count(), { timeout: 60_000 }).toBeGreaterThan(0);

  // request_id should be present for debugging.
  await expect(changeSetsPanel.getByText(/request_id/).first()).toBeVisible();
  await expect(tasksPanel.getByText(/request_id/).first()).toBeVisible();

  // Filters should work without crashing.
  await page.getByLabel("taskcenter_changeset_status", { exact: true }).selectOption("applied");
  await page.getByLabel("taskcenter_task_status", { exact: true }).selectOption("done");
  await expect.poll(async () => await changeSetItems.count(), { timeout: 60_000 }).toBeGreaterThan(0);
  await expect(tasksPanel).toBeVisible();

  // Details drawer should open.
  await changeSetItems.first().click();
  const detail = page.getByRole("dialog").filter({
    has: page.getByRole("button", { name: "复制排障信息", exact: true }),
  });
  await expect(detail).toBeVisible();
  await detail.getByRole("button", { name: "关闭", exact: true }).click();
  await expect(detail).toBeHidden();

  // Refresh keeps the status visible.
  await page.getByLabel("刷新 (taskcenter_refresh)", { exact: true }).click();
  await expect.poll(async () => await changeSetItems.count(), { timeout: 60_000 }).toBeGreaterThan(0);
});
