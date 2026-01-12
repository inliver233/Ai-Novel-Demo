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

  const card = page.getByRole("button", { name: new RegExp(title) });
  await expect(card).toBeVisible();

  await page.getByLabel("query_text", { exact: true }).fill("dragon");
  await page.getByLabel("拼接字符上限", { exact: true }).fill("10");
  await page.getByRole("button", { name: "预览", exact: true }).click();

  await expect(page.getByText("触发 1 条")).toBeVisible();
  await expect(page.getByText("已截断（超出上限）")).toBeVisible();
  await expect(page.getByText("keyword:dragon")).toBeVisible();

  await card.click();
  await expect(drawer).toBeVisible();
  await drawer.getByRole("checkbox", { name: "启用", exact: true }).uncheck();
  await drawer.getByRole("button", { name: "保存", exact: true }).click();
  await expect(drawer.getByRole("button", { name: "保存", exact: true })).toBeDisabled();
  await drawer.getByRole("button", { name: "关闭", exact: true }).click();

  await expect(card.getByText("停用", { exact: true })).toBeVisible();

  await card.click();
  await expect(drawer).toBeVisible();
  await drawer.getByRole("button", { name: "删除", exact: true }).click();
  const confirm = page.getByRole("dialog", { name: "删除该条目？", exact: true });
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", { name: "删除", exact: true }).click();

  await expect(page.getByText("暂无条目", { exact: true })).toBeVisible();
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

  const queryInput = page.getByRole("textbox", { name: "query_text", exact: true });
  await queryInput.fill("the");
  await page.getByRole("button", { name: "预览", exact: true }).click();
  await expect(page.getByText("触发 0 条")).toBeVisible();
  await expect(page.getByText("keyword:word:he | priority:important", { exact: true })).toHaveCount(0);

  await queryInput.fill("he");
  await page.getByRole("button", { name: "预览", exact: true }).click();
  await expect(page.getByText("触发 1 条")).toBeVisible();
  await expect(page.getByText("keyword:word:he | priority:important", { exact: true })).toBeVisible();
});
