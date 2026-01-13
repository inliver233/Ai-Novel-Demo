import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

test("ui: worldbook CRUD + preview_trigger", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);
  await page.setViewportSize({ width: 1280, height: 1600 });

  await page.goto(`/projects/${projectId}/worldbook`);
  await expect(page.getByText("条目列表", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "新建条目", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "编辑世界书条目", exact: true });
  await expect(drawer).toBeVisible();

  const title = "E2E WorldBook Entry";
  await drawer.getByLabel("标题", { exact: true }).fill(title);
  await drawer.getByLabel("关键词（每行一个）").fill("dragon");
  await drawer.getByLabel("内容（Markdown）", { exact: true }).fill("E2E_WB_CONTENT dragon");

  await drawer.getByRole("button", { name: "保存", exact: true }).click();
  await expect(drawer.getByRole("button", { name: "保存", exact: true })).toBeDisabled();
  await drawer.getByRole("button", { name: "关闭", exact: true }).click();
  await expect(drawer).toBeHidden();

  const card = page.getByRole("button", { name: new RegExp(title) });
  await expect(card).toBeVisible();

  const previewPanel = page.locator("div.panel:visible").filter({ hasText: "预览触发" }).first();
  await expect(previewPanel).toBeVisible();
  await previewPanel.getByLabel("query_text", { exact: true }).fill("dragon");
  await previewPanel.getByLabel("拼接字符上限", { exact: true }).fill("10");
  await previewPanel.getByRole("button", { name: "预览", exact: true }).click();

  await expect(previewPanel.getByText("触发 1 条")).toBeVisible();
  await expect(previewPanel.getByText("已截断（超出上限）")).toBeVisible();
  await expect(previewPanel.getByText("keyword:dragon")).toBeVisible();

  await card.click();
  await expect(drawer).toBeVisible();
  await drawer.getByRole("checkbox", { name: "启用", exact: true }).uncheck();
  await drawer.getByRole("button", { name: "保存", exact: true }).click();
  await expect(drawer.getByRole("button", { name: "保存", exact: true })).toBeDisabled();
  await drawer.getByRole("button", { name: "关闭", exact: true }).click();
  await expect(drawer).toBeHidden();

  await expect(card.getByText("停用", { exact: true })).toBeVisible();

  await card.click();
  await expect(drawer).toBeVisible();
  await drawer.getByRole("button", { name: "删除", exact: true }).click();
  const confirm = page.getByRole("dialog", { name: "删除该条目？", exact: true });
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", { name: "删除", exact: true }).click();

  await expect(page.getByText("暂无条目", { exact: true })).toBeVisible();
});

test("ui: worldbook preview_trigger works in drawer mode", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);
  await page.setViewportSize({ width: 1280, height: 1600 });

  await page.goto(`/projects/${projectId}/worldbook`);
  await expect(page.getByText("条目列表", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "新建条目", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "编辑世界书条目", exact: true });
  await expect(drawer).toBeVisible();

  const title = "E2E WB Drawer Preview";
  await drawer.getByLabel("标题", { exact: true }).fill(title);
  await drawer.getByLabel("关键词（每行一个）").fill("dragon");
  await drawer.getByLabel("内容（Markdown）", { exact: true }).fill("E2E_WB_CONTENT dragon");

  await drawer.getByRole("button", { name: "保存", exact: true }).click();
  await expect(drawer.getByRole("button", { name: "保存", exact: true })).toBeDisabled();

  // Page-level preview is disabled while editing drawer is open (avoid misclick on editor controls).
  const pagePreviewBtn = page.locator('button[title="编辑抽屉打开时请在抽屉内使用预览触发。"]');
  await expect(pagePreviewBtn).toBeVisible();
  await expect(pagePreviewBtn).toBeDisabled();

  await drawer.getByLabel("query_text", { exact: true }).fill("dragon");
  await drawer.getByLabel("拼接字符上限", { exact: true }).fill("10");
  await drawer.getByRole("button", { name: "预览", exact: true }).click();

  await expect(drawer.getByText("触发 1 条")).toBeVisible();
  await expect(drawer.getByText("已截断（超出上限）")).toBeVisible();

  await drawer.locator("summary", { hasText: "触发条目" }).click();
  await expect(drawer.getByText("keyword:dragon | priority:important", { exact: true })).toBeVisible();
});

test("ui: worldbook keyword boundary avoids substring false positive", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);
  await page.setViewportSize({ width: 1280, height: 1600 });

  await page.goto(`/projects/${projectId}/worldbook`);
  await expect(page.getByText("条目列表", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "新建条目", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "编辑世界书条目", exact: true });
  await expect(drawer).toBeVisible();

  const title = "E2E WB Boundary";
  await drawer.getByLabel("标题", { exact: true }).fill(title);
  await drawer.getByLabel("关键词（每行一个）").fill("word:he");
  await drawer.getByLabel("内容（Markdown）", { exact: true }).fill("E2E_WB_BOUNDARY");
  const save = drawer.getByRole("button", { name: "保存", exact: true });
  await save.scrollIntoViewIfNeeded();
  await save.click();
  await expect(drawer.getByRole("button", { name: "保存", exact: true })).toBeDisabled();
  await drawer.getByRole("button", { name: "关闭", exact: true }).click();

  await expect(page.getByRole("button", { name: new RegExp(title) })).toBeVisible();

  const previewPanel = page.locator("div.panel:visible").filter({ hasText: "预览触发" }).first();
  await expect(previewPanel).toBeVisible();
  const queryInput = previewPanel.getByRole("textbox", { name: "query_text", exact: true });
  await queryInput.fill("the");
  await previewPanel.getByRole("button", { name: "预览", exact: true }).click();
  await expect(previewPanel.getByText("触发 0 条")).toBeVisible();
  await expect(previewPanel.getByText("keyword:word:he | priority:important", { exact: true })).toHaveCount(0);

  await queryInput.fill("he");
  await previewPanel.getByRole("button", { name: "预览", exact: true }).click();
  await expect(previewPanel.getByText("触发 1 条")).toBeVisible();
  await expect(previewPanel.getByText("keyword:word:he | priority:important", { exact: true })).toBeVisible();
});
