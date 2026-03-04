import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

test("ui: outline stream generation -> apply -> create chapter skeletons", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  await page.goto(`/projects/${projectId}/outline`);
  await expect(page.getByRole("button", { name: "AI 生成大纲" })).toBeVisible();

  await page.getByRole("button", { name: "AI 生成大纲" }).click();
  await expect(page.getByRole("dialog", { name: "AI 生成大纲" })).toBeVisible();

  const streamCheckbox = page.getByRole("checkbox", { name: "流式生成（beta）" });
  await streamCheckbox.check();

  await page.getByRole("button", { name: "生成", exact: true }).click();

  await expect(page.getByText("实时章节预览（JSON）")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("生成结果预览")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/解析章节：\s*3/)).toBeVisible();

  await page.getByRole("button", { name: "覆盖当前大纲并保存" }).click();

  // Main editor should now contain the generated outline.
  await expect(page.locator('textarea[name="outline_content_md"]')).toContainText("大纲（E2E）");

  await page.getByRole("button", { name: "从大纲创建章节骨架" }).click();
  await page.getByRole("button", { name: "创建", exact: true }).click();

  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/writing$`));
  await expect(page.getByText("共 3 章")).toBeVisible();
});
