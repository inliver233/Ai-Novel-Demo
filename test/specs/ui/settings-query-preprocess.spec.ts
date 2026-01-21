import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

test("ui: settings query_preprocessing saves and shows normalized query in ContextPreviewDrawer", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  const expandSettingsSection = async (title: string) => {
    const summary = page.locator("summary", { hasText: title });
    await expect(summary).toBeVisible();
    const details = summary.locator("..");
    if ((await details.getAttribute("open")) === null) {
      await summary.click();
      await expect(details).toHaveAttribute("open", "");
    }
  };

  await page.goto(`/projects/${projectId}/settings`);
  await expect(page.getByText("项目信息", { exact: true })).toBeVisible();

  const qpTitle = page.getByText("Query 预处理（Query Preprocessing）", { exact: true });
  await expect(qpTitle).toBeVisible();
  await expandSettingsSection("Query 预处理（Query Preprocessing）");

  const enable = page.getByRole("checkbox", { name: "启用 query_preprocessing（默认关闭）", exact: true });
  await enable.check();

  await page.locator('textarea[name="query_preprocessing_tags"]').fill("foo");
  await page.locator('textarea[name="query_preprocessing_exclusion_rules"]').fill("REMOVE");
  await page.getByRole("checkbox", { name: /index_ref_enhance/, exact: false }).check();

  const save = page.getByRole("button", { name: "保存", exact: true });
  await expect(save).toBeEnabled();
  await save.click();
  await expect(save).toBeDisabled();

  await expandSettingsSection("Query 预处理（Query Preprocessing）");

  const previewBox = page.getByText("示例 normalize（基于已保存的 effective 配置）", { exact: true });
  await expect(previewBox).toBeVisible();

  const previewQuery = page.locator('textarea[placeholder="例如：回顾第1章 #foo REMOVE"]');
  await previewQuery.fill("hello #foo #bar REMOVE 回顾第12章");
  await page.getByRole("button", { name: "预览", exact: true }).click();

  const normalizedPre = page.getByText("normalized_query_text", { exact: true }).locator("..").locator("pre");
  await expect(normalizedPre).toContainText("#bar");
  await expect(normalizedPre).toContainText("chapter:12");
  await expect(normalizedPre).not.toContainText("#foo");
  await expect(normalizedPre).not.toContainText("REMOVE");

  await page.goto(`/projects/${projectId}/writing`);
  await page.getByRole("button", { name: "上下文预览", exact: true }).click();

  const dialog = page.getByRole("dialog", { name: "上下文预览" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Vector RAG 调试", { exact: true })).toBeVisible();

  const queryInput = dialog.getByLabel("query_text", { exact: true });
  await queryInput.fill("hello #foo #bar REMOVE 回顾第12章");
  await dialog.getByRole("button", { name: "查询", exact: true }).click();

  const preprocessSummary = dialog.locator("summary", { hasText: "query preprocess（raw vs normalized）" });
  await preprocessSummary.click();
  const preprocessDetails = preprocessSummary.locator("..");
  await expect(preprocessDetails).toHaveAttribute("open", "");

  const normalizedQueryPre = preprocessDetails.getByText("normalized_query_text", { exact: true }).locator("..").locator("pre");
  await expect(normalizedQueryPre).toContainText("#bar");
  await expect(normalizedQueryPre).toContainText("chapter:12");
  await expect(normalizedQueryPre).not.toContainText("#foo");
  await expect(normalizedQueryPre).not.toContainText("REMOVE");
});
