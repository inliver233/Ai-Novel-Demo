import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

test("ui: core pages navigate and render", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  await page.goto("/");
  await expect(page.getByRole("button", { name: "新建项目" })).toBeVisible();

  await page.goto(`/projects/${projectId}/writing`);
  await expect(page.getByRole("button", { name: "新增章节" })).toBeVisible();

  await page.getByRole("link", { name: "设定" }).click();
  await expect(page.getByText("项目信息")).toBeVisible();

  await page.getByRole("link", { name: "角色卡" }).click();
  await expect(page.getByRole("button", { name: "新增角色", exact: true })).toBeVisible();

  await page.getByRole("link", { name: "大纲" }).click();
  await expect(page.getByRole("button", { name: "AI 生成大纲", exact: true })).toBeVisible();

  await page.getByRole("link", { name: "模型配置" }).click();
  await expect(page.getByText("Provider", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Prompt Studio" }).click();
  await expect(page.getByRole("button", { name: "一键启用推荐预设（大纲/章节）", exact: true })).toBeVisible();

  await page.getByRole("link", { name: "预览" }).click();
  await expect(page.getByRole("button", { name: "上一章", exact: true })).toBeVisible();

  await page.getByRole("link", { name: "导出" }).click();
  await expect(page.getByText("导出 Markdown")).toBeVisible();
});
