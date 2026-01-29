import { type Page } from "@playwright/test";
import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

async function stabilizeUi(page: Page): Promise<void> {
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        transition: none !important;
        animation: none !important;
        caret-color: transparent !important;
      }
    `,
  });
}

test("ui: visual smoke (update with --update-snapshots)", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  await page.setViewportSize({ width: 1280, height: 720 });

  // Make the dashboard stable: keep a single project so the page height/layout is deterministic.
  const projectsRes = await request.get(`${state.backendUrl}/api/projects`);
  const projectsJson = (await projectsRes.json()) as { ok: boolean; data: { projects: Array<{ id: string }> } };
  for (const p of projectsJson.data.projects) {
    if (p.id === projectId) continue;
    await request.delete(`${state.backendUrl}/api/projects/${p.id}`);
  }

  await page.goto("/");
  await stabilizeUi(page);
  await expect(page.getByRole("button", { name: /E2E Project 类型：Test/ })).toBeVisible();
  await expect(page.getByText("计算完成度...", { exact: true })).toHaveCount(0);
  await expect(page).toHaveScreenshot("dashboard.png");

  await page.goto(`/projects/${projectId}/outline`);
  await stabilizeUi(page);
  await expect(page.getByText("当前大纲", { exact: true })).toBeVisible();
  await expect(page.locator('select[name="active_outline_id"]')).toHaveValue(/.+/);
  await expect(page).toHaveScreenshot("outline.png");

  await page.goto(`/projects/${projectId}/writing`);
  await stabilizeUi(page);
  await expect(page.getByText("请选择或新建章节开始写作。", { exact: true })).toBeVisible();
  await expect(page).toHaveScreenshot("writing-empty.png");

  await page.goto(`/projects/${projectId}/rag`);
  await stabilizeUi(page);
  await expect(page.getByText("Vector RAG 管理", { exact: true })).toBeVisible();
  await expect(page).toHaveScreenshot("rag.png");

  await page.goto(`/projects/${projectId}/graph`);
  await stabilizeUi(page);
  await expect(page.getByLabel("graph_query_text", { exact: true })).toBeVisible();
  await expect(page).toHaveScreenshot("graph.png");

  await page.goto(`/projects/${projectId}/fractal`);
  await stabilizeUi(page);
  await expect(page.getByText("分形记忆（Fractal）", { exact: true })).toBeVisible();
  await expect(page).toHaveScreenshot("fractal.png");

  await page.goto(`/projects/${projectId}/tasks`);
  await stabilizeUi(page);
  await expect(page.getByRole("region", { name: "变更集 (taskcenter_changesets_section)", exact: true })).toBeVisible();
  await expect(page.getByText("暂无变更集", { exact: true })).toBeVisible();
  await expect(page.getByText("暂无任务", { exact: true })).toBeVisible();
  await expect(page).toHaveScreenshot("task-center.png");

  await page.goto(`/projects/${projectId}/structured-memory`);
  await stabilizeUi(page);
  await expect(page.getByRole("button", { name: /structured_tab_entities/ })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("暂无数据", { exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page).toHaveScreenshot("structured-memory.png");

  await page.goto(`/projects/${projectId}/prompt-studio`);
  await stabilizeUi(page);
  await expect(page.getByText("提示词工作室（beta）", { exact: true })).toBeVisible();
  await expect(page).toHaveScreenshot("prompt-studio.png");

  await page.goto(`/projects/${projectId}/settings`);
  await stabilizeUi(page);
  await expect(page.getByText("项目信息", { exact: true })).toBeVisible();
  await expect(page).toHaveScreenshot("settings.png");

  // Capture sidebar advanced-debug section to cover nav icon changes (RAG / Glossary / etc).
  const expandSidebar = page.getByRole("button", { name: "展开侧边栏", exact: true });
  if (await expandSidebar.isVisible()) await expandSidebar.click();

  const advancedToggle = page.getByLabel("显示高级调试 (toggle_advanced_debug)", { exact: true });
  await expect(advancedToggle).toBeVisible();
  await advancedToggle.check();

  const sidebar = page.locator("aside").first();
  const navRag = sidebar.getByLabel("知识库（RAG） (nav_rag)", { exact: true });
  if (!(await navRag.isVisible())) {
    const summary = sidebar.locator("summary", { hasText: "高级调试" }).first();
    await expect(summary).toBeVisible();
    await summary.scrollIntoViewIfNeeded();
    await summary.click();
    await expect(navRag).toBeVisible();
  }

  const advancedDebugDetails = sidebar.locator("details").filter({ hasText: "高级调试" }).first();
  await expect(advancedDebugDetails).toHaveScreenshot("sidebar-advanced-debug.png");
});
