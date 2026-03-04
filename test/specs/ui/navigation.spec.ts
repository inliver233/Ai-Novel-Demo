import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

test("ui: core pages navigate and render", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  await page.goto("/");
  await expect(page.getByRole("button", { name: "新建项目" })).toBeVisible();

  await page.goto(`/projects/${projectId}/writing`);
  await expect(page.getByRole("button", { name: "新增章节" })).toBeVisible();

  // Ensure sidebar is expanded so the advanced debug toggle is always available.
  const expandSidebar = page.getByRole("button", { name: "展开侧边栏", exact: true });
  if (await expandSidebar.isVisible()) await expandSidebar.click();

  const advancedToggle = page.getByLabel("显示高级调试 (toggle_advanced_debug)", { exact: true });
  await expect(advancedToggle).toBeVisible();

  // Off: advanced debug pages should not be visible.
  await advancedToggle.uncheck();
  await expect(page.getByLabel("知识库（RAG） (nav_rag)", { exact: true })).toHaveCount(0);

  const openAdvancedDebugGroup = async () => {
    const navRag = page.getByLabel("知识库（RAG） (nav_rag)", { exact: true });
    if (await navRag.isVisible()) return;

    const sidebar = page.locator("aside").first();
    const summary = sidebar.locator("summary", { hasText: "高级调试" }).first();
    await expect(summary).toBeVisible();
    await summary.scrollIntoViewIfNeeded();
    await summary.click();
    await expect(navRag).toBeVisible();
  };

  await page.getByLabel("项目设置 (nav_settings)", { exact: true }).click();
  await expect(page.getByText("项目信息")).toBeVisible();

  await page.getByLabel("角色卡 (nav_characters)", { exact: true }).click();
  await expect(page.getByRole("button", { name: "新增角色", exact: true }).first()).toBeVisible();

  await page.getByLabel("大纲 (nav_outline)", { exact: true }).click();
  await expect(page.getByRole("button", { name: "AI 生成大纲", exact: true })).toBeVisible();

  await page.getByLabel("模型配置 (nav_prompts)", { exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/prompts$`));
  await expect(page.getByRole("heading", { name: "模型配置", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "测试连接", exact: true })).toBeVisible();

  await page.getByLabel("提示词工作室 (nav_prompt_studio)", { exact: true }).click();
  await expect(page.getByRole("button", { name: "一键启用推荐预设（大纲/章节）", exact: true })).toBeVisible();

  await page.getByLabel("预览 (nav_preview)", { exact: true }).click();
  await expect(page.getByRole("button", { name: "上一章", exact: true })).toBeVisible();

  // On: advanced debug pages should be reachable and selectors should be stable.
  await advancedToggle.check();

  await openAdvancedDebugGroup();

  await page.getByLabel("知识库（RAG） (nav_rag)", { exact: true }).click();
  await expect(page.getByText("Vector RAG 管理", { exact: true })).toBeVisible();

  await page.getByLabel("图谱/关系 (nav_graph)", { exact: true }).click();
  await expect(page.getByLabel("graph_enabled", { exact: true })).toBeVisible();

  await openAdvancedDebugGroup();
  await page.getByLabel("分形（Fractal） (nav_fractal)", { exact: true }).click();
  await expect(page.getByText("Fractal", { exact: true })).toBeVisible();

  await openAdvancedDebugGroup();
  await page.getByLabel("图谱底座数据 (nav_structured_memory)", { exact: true }).click();
  await expect(page.getByLabel("structured_search", { exact: true })).toBeVisible();

  await openAdvancedDebugGroup();
  await page.getByLabel("任务中心 (nav_tasks)", { exact: true }).click();
  await expect(page.getByLabel("刷新 (taskcenter_refresh)", { exact: true })).toBeVisible();

  // NOTE: WizardNextBar (fixed footer) may overlap the sidebar bottom; use direct navigation to keep this smoke stable.
  await page.goto(`/projects/${projectId}/export`);
  await expect(page.getByRole("button", { name: "导出 Markdown", exact: true })).toBeVisible();
});
