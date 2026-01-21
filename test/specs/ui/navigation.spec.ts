import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

test("ui: core pages navigate and render", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  await page.goto("/");
  await expect(page.getByRole("button", { name: "新建项目" })).toBeVisible();

  await page.goto(`/projects/${projectId}/writing`);
  await expect(page.getByRole("button", { name: "新增章节" })).toBeVisible();

  await page.getByLabel("项目设置 (nav_settings)", { exact: true }).click();
  await expect(page.getByText("项目信息")).toBeVisible();

  await page.getByLabel("角色卡 (nav_characters)", { exact: true }).click();
  await expect(page.getByRole("button", { name: "新增角色", exact: true })).toBeVisible();

  await page.getByLabel("大纲 (nav_outline)", { exact: true }).click();
  await expect(page.getByRole("button", { name: "AI 生成大纲", exact: true })).toBeVisible();

  await page.getByLabel("模型配置 (nav_prompts)", { exact: true }).click();
  await expect(page.getByText("Provider", { exact: true })).toBeVisible();

  await page.getByLabel("提示词工作室 (nav_prompt_studio)", { exact: true }).click();
  await expect(page.getByRole("button", { name: "一键启用推荐预设（大纲/章节）", exact: true })).toBeVisible();

  await page.getByLabel("预览 (nav_preview)", { exact: true }).click();
  await expect(page.getByRole("button", { name: "上一章", exact: true })).toBeVisible();

  // NOTE: WizardNextBar (fixed footer) may overlap the sidebar bottom; use direct navigation to keep this smoke stable.
  await page.goto(`/projects/${projectId}/export`);
  await expect(page.getByText("导出 Markdown")).toBeVisible();
});
