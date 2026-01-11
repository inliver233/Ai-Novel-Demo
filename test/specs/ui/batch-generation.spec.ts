import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: batch generation -> apply to editor -> history visible", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const bulk = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters/bulk_create`, {
    data: {
      chapters: [
        { number: 1, title: "第 1 章", plan: "计划 1" },
        { number: 2, title: "第 2 章", plan: "计划 2" },
        { number: 3, title: "第 3 章", plan: "计划 3" },
      ],
    },
  });
  expect(bulk.ok()).toBeTruthy();
  const bulkJson = (await bulk.json()) as { ok: boolean; data: { chapters: Array<{ id: string; number: number }> } };
  const chapter1 = bulkJson.data.chapters.find((c) => c.number === 1);
  expect(chapter1?.id).toBeTruthy();

  const seedText = "__SEED_CH1__";

  // Batch generation enforces sequential prerequisites; make chapter 1 non-empty.
  const seed = await request.put(`${state.backendUrl}/api/chapters/${chapter1!.id}`, {
    data: { content_md: seedText },
  });
  expect(seed.ok()).toBeTruthy();

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapter1!.id}`);
  await expect(page.getByRole("button", { name: "批量生成", exact: false })).toBeVisible();

  await page.getByRole("button", { name: "批量生成", exact: false }).click();
  const modal = page.getByRole("dialog", { name: "批量生成" });
  await expect(modal).toBeVisible();

  // Keep it fast: generate 1 chapter after the active one.
  const countInput = modal.getByRole("spinbutton");
  await countInput.fill("1");

  await modal.getByRole("button", { name: "开始批量生成", exact: true }).click();

  await expect(modal.getByText(/任务状态：/)).toBeVisible({ timeout: 60_000 });

  const apply = modal.getByRole("button", { name: "应用到编辑器", exact: true }).first();
  await expect(apply).toBeVisible({ timeout: 60_000 });
  await apply.click();

  // Applying a batch item closes the modal and may prompt if the chapter is dirty.
  await expect(modal).toBeHidden({ timeout: 60_000 });
  const applyConfirm = page.getByRole("dialog", { name: "章节有未保存修改，是否应用生成记录？" });
  const leaveConfirm = page.getByRole("dialog", { name: "有未保存修改，确定离开？" });
  const dismissApplyConfirmIfPresent = async () => {
    try {
      if (await applyConfirm.isVisible()) {
        await applyConfirm.getByRole("button", { name: "直接应用（不保存）", exact: true }).click();
        await expect(applyConfirm).toBeHidden({ timeout: 60_000 });
      }
    } catch {
      // Noop: confirm may not exist.
    }
  };
  const dismissLeaveConfirmIfPresent = async () => {
    try {
      if (await leaveConfirm.isVisible()) {
        await leaveConfirm.getByRole("button", { name: "离开", exact: true }).click();
        await expect(leaveConfirm).toBeHidden({ timeout: 60_000 });
      }
    } catch {
      // Noop: confirm may not exist.
    }
  };
  try {
    await applyConfirm.waitFor({ state: "visible", timeout: 10_000 });
    await applyConfirm.getByRole("button", { name: "直接应用（不保存）", exact: true }).click();
    await expect(applyConfirm).toBeHidden({ timeout: 60_000 });
  } catch {
    // Noop: confirm may not appear.
  }
  await dismissLeaveConfirmIfPresent();

  const content = page.locator('textarea[name="content_md"]:visible');
  await expect(content).toHaveValue(/E2E/, { timeout: 60_000 });
  await expect(content).not.toHaveValue(new RegExp(seedText));

  const openHistory = page.getByRole("button", { name: "生成记录", exact: true });
  try {
    await openHistory.click({ timeout: 5_000 });
  } catch {
    await dismissApplyConfirmIfPresent();
    await dismissLeaveConfirmIfPresent();
    await openHistory.click({ timeout: 60_000 });
  }
  const drawer = page.getByRole("dialog", { name: "生成记录" });
  await expect(drawer).toBeVisible();

  // Ensure there is at least one run and can be selected.
  const firstRun = drawer.locator("button").filter({ hasText: "ok" }).first();
  await expect(firstRun).toBeVisible({ timeout: 60_000 });
  await firstRun.click();
  await expect(drawer.getByText("output / error")).toBeVisible();
});
