import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

test("ui: task center shows effective queue backend + health request_id", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  await page.goto(`/projects/${projectId}/tasks`);

  const banner = page.getByRole("region", { name: "队列状态 (taskcenter_queue_status)", exact: true });
  await expect(banner).toBeVisible({ timeout: 60_000 });
  await expect(banner).toContainText("queue_backend");
  await expect(banner).toContainText("effective_backend");
  await expect(banner).toContainText("inline");

  await expect(banner.getByRole("button", { name: "复制 health 请求 ID（request_id）", exact: true })).toBeVisible();

  const projectTasksPanel = page.getByRole("region", { name: "项目任务 (taskcenter_projecttasks_section)", exact: true });
  await expect(projectTasksPanel).toBeVisible();
});

