import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

test("ui: style profiles create and set project default", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);
  const styleName = `E2E 自定义风格 ${Date.now()}`;

  await page.goto(`/projects/${projectId}/styles`);
  await expect(page.getByRole("heading", { name: "风格", exact: true })).toBeVisible();
  await expect(page.getByText("系统预设", { exact: true })).toBeVisible();
  await expect(page.getByText("我的风格", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "新建风格" }).click();
  await expect(page.getByRole("dialog", { name: "新建风格" })).toBeVisible();

  await page.getByLabel("style_name", { exact: true }).fill(styleName);
  await page.getByLabel("style_description", { exact: true }).fill("for test");
  await page.getByLabel("style_prompt_content", { exact: true }).fill("写作要求：\n- E2E 测试风格\n");

  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByText(styleName, { exact: true })).toBeVisible();

  await page.getByRole("button", { name: `设为默认:${styleName}`, exact: true }).click();
  await expect(page.getByLabel("project_default_style", { exact: true })).toContainText(styleName);

  await page.reload();
  await expect(page.getByLabel("project_default_style", { exact: true })).toContainText(styleName);
});
