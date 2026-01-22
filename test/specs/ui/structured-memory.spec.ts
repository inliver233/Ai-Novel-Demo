import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: structured memory page tabs + search + memory update drawer", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "用于 StructuredMemory", status: "done" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as { ok: boolean; data: { chapter: { id: string } } };
  const chapterId = createJson.data.chapter.id;

  // Seed at least one entity via Memory Update.
  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);
  await expect(page.getByRole("textbox", { name: "标题", exact: true })).toHaveValue("E2E 第一章", { timeout: 60_000 });
  await page.getByRole("button", { name: "Memory Update", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "记忆更新（Memory Update）" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "一键生成提议（Auto Propose）", exact: true }).click();
  await expect(dialog.getByText("步骤 2：审核（Review）", { exact: true })).toBeVisible({ timeout: 60_000 });
  await dialog.getByRole("button", { name: "应用已接受项（Apply）", exact: true }).click();
  await expect(dialog.getByText("应用结果（Apply Result）", { exact: true })).toBeVisible({ timeout: 60_000 });
  await dialog.getByRole("button", { name: "关闭", exact: true }).click();
  await expect(dialog).toBeHidden();

  await page.goto(`/projects/${projectId}/structured-memory?chapterId=${chapterId}`);
  await expect(page.getByRole("button", { name: /structured_tab_entities/ })).toBeVisible({ timeout: 60_000 });

  // Entities should include the seeded entity.
  await expect(page.getByText("character:Alice", { exact: true })).toBeVisible({ timeout: 60_000 });

  // Search filter should work.
  await page.getByLabel("structured_search", { exact: true }).fill("Alice");
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  await expect(page.getByText("character:Alice", { exact: true })).toBeVisible({ timeout: 60_000 });

  // Tabs should switch without crashing.
  await page.getByRole("button", { name: /structured_tab_relations/ }).click();
  await expect(page.getByText("暂无数据", { exact: true })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: /structured_tab_events/ }).click();
  await expect(page.getByText("暂无数据", { exact: true })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: /structured_tab_foreshadows/ }).click();
  await expect(page.getByText("暂无数据", { exact: true })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: /structured_tab_evidence/ }).click();
  await expect(page.getByText("暂无数据", { exact: true })).toBeVisible({ timeout: 60_000 });

  // MemoryUpdateDrawer should be available on this page when chapterId is present.
  await page.getByRole("button", { name: "Memory Update", exact: true }).click();
  const dialog2 = page.getByRole("dialog", { name: "记忆更新（Memory Update）" });
  await expect(dialog2).toBeVisible({ timeout: 60_000 });
  await dialog2.getByRole("button", { name: "关闭", exact: true }).click();
  await expect(dialog2).toBeHidden();
});
