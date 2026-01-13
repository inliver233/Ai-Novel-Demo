import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

test("ui: rag page supports status + query injection preview", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  await page.goto(`/projects/${projectId}/rag`);
  await expect(page.getByText("Vector RAG 管理", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "刷新状态", exact: true }).click();
  await expect(page.getByText(/disabled_reason:/)).toBeVisible();

  const queryInput = page.getByLabel("query_text", { exact: true });
  await queryInput.fill("dragon");
  await page.getByRole("button", { name: "查询", exact: true }).click();

  await expect(page.getByText("注入预览（prompt_block.text_md）", { exact: true })).toBeVisible();

  const rawSummary = page.locator("summary", { hasText: "raw vector query result" });
  await rawSummary.click();
  const rawDetails = rawSummary.locator("..");
  await expect(rawDetails).toHaveAttribute("open", "");
  await expect(rawDetails).toContainText('"query_text": "dragon"');
});

