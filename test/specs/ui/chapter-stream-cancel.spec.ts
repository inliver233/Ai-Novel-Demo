import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: chapter stream can be canceled and reverts editor", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as { ok: boolean; data: { chapter: { id: string } } };
  const chapterId = createJson.data.chapter.id;

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);
  const content = page.locator('textarea[name="content_md"]');
  await expect(content).toHaveValue("");

  await page.getByRole("button", { name: "AI 生成", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "AI 生成", exact: true });
  await expect(drawer).toBeVisible();

  await drawer.getByRole("button", { name: "高级参数", exact: true }).click();
  await drawer.getByRole("checkbox", { name: "流式生成（beta）", exact: true }).check();
  await drawer.locator('textarea[name="instruction"]').fill("E2E_LONG_STREAM");

  await drawer.getByRole("button", { name: "生成", exact: true }).click();
  await expect(content).not.toHaveValue("", { timeout: 30_000 });

  const cancelBtn = drawer.getByRole("button", { name: "取消生成", exact: true });
  await expect(cancelBtn).toBeVisible({ timeout: 30_000 });
  await cancelBtn.click();

  await expect(page.getByText("已取消生成")).toBeVisible();
  await expect(content).toHaveValue("");
});
