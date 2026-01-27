import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

test("ui: prompt inspector precheck supports override + revert", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  await page.goto(`/projects/${projectId}/writing`);
  await expect(page.getByRole("button", { name: "新增章节" })).toBeVisible();

  await page.getByRole("button", { name: "新增章节" }).click();
  await expect(page.getByRole("dialog", { name: "新增章节" })).toBeVisible();

  await page.locator('input[name="number"]').fill("1");
  await page.locator('input[name="title"]').fill("E2E 第一章");
  await page.locator('textarea[name="plan"]').fill("要点 A；要点 B");
  await page.getByRole("button", { name: "创建", exact: true }).click();

  await expect(page.getByRole("button", { name: "AI 生成", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "AI 生成", exact: true }).click();
  const genDrawer = page.getByRole("dialog", { name: "AI 生成", exact: true });
  await expect(genDrawer).toBeVisible();

  await genDrawer.getByRole("button", { name: /^预检\/审查/, exact: false }).click();

  const inspector = page.getByRole("dialog", { name: "Prompt Inspector", exact: true });
  await expect(inspector).toBeVisible();
  await expect(inspector.getByText("task: chapter_generate", { exact: true })).toBeVisible();

  await inspector.getByLabel("prompt_override_user", { exact: true }).fill("E2E override user");
  await inspector.getByRole("button", { name: "使用覆盖文本执行", exact: true }).click();
  await expect(inspector).not.toBeVisible();

  const content = page.locator('textarea[name="content_md"]');
  await expect(content).not.toHaveValue("", { timeout: 30_000 });
  await expect(content).toContainText("E2E");

  await expect(genDrawer.getByRole("button", { name: "回退默认", exact: true })).toBeVisible();
  await genDrawer.getByRole("button", { name: "回退默认", exact: true }).click();
  await expect(genDrawer.getByRole("button", { name: "回退默认", exact: true })).toHaveCount(0);
});
