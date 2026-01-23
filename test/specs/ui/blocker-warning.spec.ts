import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

test("ui: blocker warning not emitted across dirty navigation", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  const blockerWarnings: string[] = [];
  page.on("console", (msg) => {
    const text = msg.text();
    if (text.includes("A router only supports one blocker at a time")) blockerWarnings.push(text);
  });

  await page.goto(`/projects/${projectId}/settings`);
  await expect(page.getByText("项目信息", { exact: true })).toBeVisible();

  // Make Settings dirty without auto-save interference.
  const vectorPanel = page.locator('details[aria-label="向量检索（Vector RAG）"]');
  await vectorPanel.evaluate((el) => ((el as HTMLDetailsElement).open = true));
  const embeddingPanel = vectorPanel.locator("details").filter({ hasText: "Embedding（向量化）配置" });
  await embeddingPanel.evaluate((el) => ((el as HTMLDetailsElement).open = true));
  await expect(
    vectorPanel.getByRole("button", { name: "恢复使用后端环境变量（清除项目覆盖）", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "恢复使用后端环境变量（清除项目覆盖）", exact: true }).click();
  await expect(page.getByRole("button", { name: "保存", exact: true })).toBeEnabled();

  await page.getByLabel("大纲 (nav_outline)", { exact: true }).click();
  const leave1 = page.getByRole("dialog", { name: "有未保存修改，确定离开？", exact: true });
  await expect(leave1).toBeVisible();
  await leave1.getByRole("button", { name: "离开", exact: true }).click();
  await expect(leave1).toBeHidden();

  await expect(page.getByRole("button", { name: "保存大纲", exact: true })).toBeVisible();
  await page.locator('textarea[name="outline_content_md"]').fill(`E2E_OUTLINE_DIRTY_${Date.now()}`);
  await expect(page.getByRole("button", { name: "保存大纲", exact: true })).toBeEnabled();

  await page.getByLabel("模型配置 (nav_prompts)", { exact: true }).click();
  const leave2 = page.getByRole("dialog", { name: "有未保存修改，确定离开？", exact: true });
  await expect(leave2).toBeVisible();
  await leave2.getByRole("button", { name: "离开", exact: true }).click();
  await expect(leave2).toBeHidden();

  await expect(page.getByRole("heading", { name: "模型配置", exact: true })).toBeVisible();
  await page.locator('input[name="model"]').fill(`e2e-model-${Date.now()}`);

  // Router warnings are emitted synchronously, but leave a tick for any deferred logs.
  await page.waitForTimeout(200);
  expect(blockerWarnings).toHaveLength(0);
});
