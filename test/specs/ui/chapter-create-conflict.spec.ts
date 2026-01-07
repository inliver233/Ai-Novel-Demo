import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

test("ui: create chapter conflict (duplicate number) shows error", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  await page.goto(`/projects/${projectId}/writing`);
  await expect(page.getByRole("button", { name: "新增章节", exact: true })).toBeVisible();

  const createOk = page.waitForResponse(
    (resp) => resp.request().method() === "POST" && resp.url().endsWith(`/api/projects/${projectId}/chapters`) && resp.ok(),
  );
  await page.getByRole("button", { name: "新增章节", exact: true }).click();
  const dialog1 = page.getByRole("dialog", { name: "新增章节" });
  await expect(dialog1).toBeVisible();
  await dialog1.locator('input[name="number"]').fill("1");
  await dialog1.locator('input[name="title"]').fill("E2E 第一章");
  await dialog1.locator('textarea[name="plan"]').fill("要点 A");
  await dialog1.getByRole("button", { name: "创建", exact: true }).click();
  await createOk;

  const createConflict = page.waitForResponse((resp) => {
    const url = resp.url();
    return resp.request().method() === "POST" && url.endsWith(`/api/projects/${projectId}/chapters`) && resp.status() === 409;
  });
  await page.getByRole("button", { name: "新增章节", exact: true }).click();
  const dialog2 = page.getByRole("dialog", { name: "新增章节" });
  await expect(dialog2).toBeVisible();
  await dialog2.locator('input[name="number"]').fill("1");
  await dialog2.locator('input[name="title"]').fill("E2E 第一章（重复）");
  await dialog2.getByRole("button", { name: "创建", exact: true }).click();
  await createConflict;

  await expect(page.getByText(/章节号已存在/)).toBeVisible();
});
