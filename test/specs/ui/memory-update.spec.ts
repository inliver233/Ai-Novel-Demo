import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: Memory Update propose -> review -> apply", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "用于 Memory Update", status: "done" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as { ok: boolean; data: { chapter: { id: string } } };
  const chapterId = createJson.data.chapter.id;

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);

  await page.getByRole("button", { name: "Memory Update", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Memory Update" });
  await expect(dialog).toBeVisible();

  await dialog.getByRole("button", { name: "一键生成提议", exact: true }).click();
  await expect(dialog.getByText("提议 diff", { exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(dialog.getByText("entities（1）", { exact: true })).toBeVisible();

  await dialog.getByRole("button", { name: "Apply accepted", exact: true }).click();
  await expect(dialog.getByText("Apply 结果", { exact: true })).toBeVisible({ timeout: 60_000 });

  await dialog.getByRole("button", { name: "刷新", exact: true }).click();
  await expect(dialog.getByText("character:Alice", { exact: true })).toBeVisible({ timeout: 60_000 });
});
