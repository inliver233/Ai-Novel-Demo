import type { Locator } from "@playwright/test";
import { test, expect, waitForWorldbookBulkSelectedCount, waitForWorldbookEntryCardsLoaded } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

async function clickDialogButton(dialog: Locator, name: string): Promise<void> {
  const button = dialog.getByRole("button", { name, exact: true });
  await expect(button).toBeVisible();
  await button.dispatchEvent("click");
  await expect(dialog).toBeHidden({ timeout: 60_000 });
}

test("ui: Drawer closes on Escape", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  await page.goto(`/projects/${projectId}/worldbook`);
  await expect(page.getByText("条目列表", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "导入 JSON", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "世界书导入", exact: true });
  await expect(drawer).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
});

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
  await clickDialogButton(confirm, "删除");

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

  const preventRecursion = drawer.getByRole("checkbox", { name: "阻止递归", exact: true });
  const preventRecursionInitial = await preventRecursion.isChecked();

  await drawer.getByLabel("query_text", { exact: true }).fill("dragon");
  await drawer.getByLabel("拼接字符上限", { exact: true }).fill("10");
  await drawer.getByRole("button", { name: "预览", exact: true }).click();
  expect(await preventRecursion.isChecked()).toBe(preventRecursionInitial);

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

test("ui: worldbook supports search + sort", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const makeEntry = async (title: string, keyword: string, priority: "drop_first" | "optional" | "important" | "must", enabled: boolean) => {
    const res = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries`, {
      data: {
        title,
        content_md: `${title} content ${keyword}`,
        enabled,
        constant: false,
        keywords: [keyword],
        exclude_recursion: false,
        prevent_recursion: false,
        char_limit: 12000,
        priority,
      },
    });
    expect(res.ok()).toBeTruthy();
  };

  await makeEntry("Alpha", "alpha", "optional", true);
  await makeEntry("Beta", "dragon", "must", false);
  await makeEntry("Gamma", "dragon", "important", true);

  await page.goto(`/projects/${projectId}/worldbook`);
  await expect(page.getByText("条目列表", { exact: true })).toBeVisible();

  const sort = page.getByLabel("worldbook_sort", { exact: true });
  const search = page.getByLabel("worldbook_search", { exact: true });

  await sort.selectOption("priority_desc");
  const first1 = page.locator("button.panel-interactive").first();
  await expect(first1).toContainText("Beta");

  await search.fill("dragon");
  await sort.selectOption("enabled_desc");
  const first2 = page.locator("button.panel-interactive").first();
  await expect(first2).toContainText("Gamma");
});

test("ui: worldbook supports bulk actions + duplicate", async ({ page, request }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const makeEntry = async (title: string, keyword: string) => {
    const res = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries`, {
      data: {
        title,
        content_md: `${title} content ${keyword}`,
        enabled: true,
        constant: false,
        keywords: [keyword],
        exclude_recursion: false,
        prevent_recursion: false,
        char_limit: 12000,
        priority: "important",
      },
    });
    expect(res.ok()).toBeTruthy();
  };

  await makeEntry("Alpha", "alpha");
  await makeEntry("Beta", "beta");

  await page.goto(`/projects/${projectId}/worldbook`);
  await expect(page.getByText("条目列表", { exact: true })).toBeVisible();

  await waitForWorldbookEntryCardsLoaded(page, { exactCount: 2 });

  await page.getByLabel("worldbook_bulk_mode", { exact: true }).check();
  await page.getByLabel("worldbook_bulk_select_all", { exact: true }).click();
  await waitForWorldbookBulkSelectedCount(page, 2);

  await page.getByLabel("worldbook_bulk_disable", { exact: true }).click();
  const confirmDisable = page.getByRole("dialog", { name: "批量停用条目？", exact: true });
  await expect(confirmDisable).toBeVisible();
  await clickDialogButton(confirmDisable, "确认");

  await expect(page.getByRole("button", { name: /Alpha/ }).getByText("停用", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Beta/ }).getByText("停用", { exact: true })).toBeVisible();

  await page.getByLabel("worldbook_bulk_priority", { exact: true }).selectOption("must");
  await page.getByLabel("worldbook_bulk_apply_priority", { exact: true }).click();
  const confirmUpdate1 = page.getByRole("dialog", { name: "批量更新条目？", exact: true });
  await expect(confirmUpdate1).toBeVisible();
  await clickDialogButton(confirmUpdate1, "确认");
  await expect(page.getByRole("button", { name: /Alpha/ }).getByText("priority:must", { exact: true })).toBeVisible();

  await page.getByLabel("worldbook_bulk_char_limit", { exact: true }).fill("123");
  await page.getByLabel("worldbook_bulk_apply_char_limit", { exact: true }).click();
  const confirmUpdate2 = page.getByRole("dialog", { name: "批量更新条目？", exact: true });
  await expect(confirmUpdate2).toBeVisible();
  await clickDialogButton(confirmUpdate2, "确认");
  await expect(page.getByRole("button", { name: /Alpha/ }).getByText("limit:123", { exact: true })).toBeVisible();

  await page.getByLabel("worldbook_bulk_clear_selection", { exact: true }).click();
  await waitForWorldbookBulkSelectedCount(page, 0);
  await page.getByRole("button", { name: /Alpha/ }).click();
  await waitForWorldbookBulkSelectedCount(page, 1);
  await expect(page.getByLabel("worldbook_bulk_duplicate_edit", { exact: true })).toBeEnabled();
  await page.getByLabel("worldbook_bulk_duplicate_edit", { exact: true }).click();
  const confirmDuplicate = page.getByRole("dialog", { name: "复制条目？", exact: true });
  await expect(confirmDuplicate).toBeVisible();
  await clickDialogButton(confirmDuplicate, "复制");

  const drawer = page.getByRole("dialog", { name: "编辑世界书条目", exact: true });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByLabel("标题", { exact: true })).toHaveValue(/Alpha.*复制/);
  await drawer.getByRole("button", { name: "关闭", exact: true }).click();
  await expect(drawer).toBeHidden();

  await waitForWorldbookEntryCardsLoaded(page, { exactCount: 3 });

  await page.getByLabel("worldbook_bulk_mode", { exact: true }).check();
  await page.getByLabel("worldbook_bulk_select_all", { exact: true }).click();
  await waitForWorldbookBulkSelectedCount(page, 3);
  await page.getByLabel("worldbook_bulk_delete", { exact: true }).click();
  const confirmDelete = page.getByRole("dialog", { name: "批量删除条目？", exact: true });
  await expect(confirmDelete).toBeVisible();
  await clickDialogButton(confirmDelete, "删除");

  await expect(page.getByText("暂无条目", { exact: true })).toBeVisible();
});
