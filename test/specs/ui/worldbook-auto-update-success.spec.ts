import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("ui: worldbook auto_update succeeds after chapter done", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 世界书自动更新（成功）", plan: "用于 worldbook auto_update 成功链路", status: "drafting" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as ApiOk<{ chapter: { id: string } }>;
  const chapterId = createJson.data.chapter.id;

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);
  await expect(page.getByRole("textbox", { name: "标题", exact: true })).toHaveValue("E2E 世界书自动更新（成功）", {
    timeout: 60_000,
  });

  await page
    .locator('textarea[name="content_md"]')
    .fill("E2E_WORLDBOOK_SUCCESS\n\n地点：阿卡迪亚（Arcadia）。\n备注：用于验证 worldbook_auto_update create。\n");

  await page.getByRole("combobox", { name: /^状态/ }).selectOption("done");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByRole("button", { name: "保存", exact: true })).toBeDisabled({ timeout: 60_000 });

  await expect.poll(
    async () => {
      const res = await request.get(`${state.backendUrl}/api/projects/${projectId}/tasks?kind=worldbook_auto_update&limit=10`);
      if (!res.ok()) return "http_error";
      const json = (await res.json()) as ApiOk<{ items: { kind: string; status: string }[] }>;
      const items = Array.isArray(json.data?.items) ? json.data.items : [];
      const task = items.find((it) => it && it.kind === "worldbook_auto_update");
      return task?.status ?? "missing";
    },
    { timeout: 60_000 },
  ).toBe("done");

  await page.goto(`/projects/${projectId}/tasks`);
  const projectTasksPanel = page.getByRole("region", { name: "项目任务 (taskcenter_projecttasks_section)", exact: true });
  await expect(projectTasksPanel).toBeVisible({ timeout: 60_000 });

  await page.getByLabel("刷新 (taskcenter_refresh)", { exact: true }).click();
  const taskItem = projectTasksPanel.locator("button.surface").filter({ hasText: "worldbook_auto_update" }).first();
  await expect(taskItem).toBeVisible({ timeout: 60_000 });
  await expect(taskItem).toContainText("完成（done）");

  await page.goto(`/projects/${projectId}/worldbook`);
  await page.getByLabel("worldbook_search", { exact: true }).fill("阿卡迪亚");
  await expect(page.getByRole("button", { name: /E2E 城市：阿卡迪亚/ }).first()).toBeVisible({ timeout: 60_000 });
});
