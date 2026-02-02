import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("ui: writing tables panel + context preview tables injection", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "用于 TablesPanel", status: "drafting" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as ApiOk<{ chapter: { id: string } }>;
  const chapterId = createJson.data.chapter.id;

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);
  await expect(page.getByRole("textbox", { name: "标题", exact: true })).toHaveValue("E2E 第一章", { timeout: 60_000 });

  await page.getByRole("button", { name: "表格面板", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: /表格面板/ });
  await expect(dialog).toBeVisible();

  await dialog.getByLabel("create_table_name", { exact: true }).fill("E2E inventory");
  await dialog.getByRole("button", { name: "创建", exact: true }).click();
  await expect(dialog.getByRole("option", { name: /E2E inventory/ })).toHaveCount(1);

  await dialog.getByRole("button", { name: "新增行", exact: true }).click();
  const keyInput = dialog.getByLabel(/cell_.*_key$/).first();
  await expect(keyInput).toHaveValue("item_1", { timeout: 60_000 });

  await dialog.getByLabel(/cell_.*_value$/).first().fill("potion");
  await dialog.getByRole("button", { name: "保存", exact: true }).click();
  await expect(dialog.getByLabel(/cell_.*_value$/).first()).toHaveValue("potion", { timeout: 60_000 });

  await dialog.getByRole("button", { name: "关闭", exact: true }).click();
  await expect(dialog).toBeHidden();

  await page.getByRole("button", { name: "上下文预览", exact: true }).click();
  const preview = page.getByRole("dialog", { name: "上下文预览" });
  await expect(preview).toBeVisible();

  await preview.getByRole("checkbox", { name: "世界书注入", exact: true }).check();
  const tablesPanel = preview.locator("div.panel", { hasText: "Tables（sys.memory.tables）" });
  await expect(tablesPanel).toBeVisible({ timeout: 60_000 });

  const textSummary = tablesPanel.locator("summary", { hasText: /^tables\.text_md（最终注入文本）$/ });
  await textSummary.click();
  await expect(tablesPanel).toContainText("<TABLES>", { timeout: 60_000 });
  await expect(tablesPanel).toContainText("E2E inventory");
  await expect(tablesPanel).toContainText("item_1");
});
