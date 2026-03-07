import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: batch generation -> apply to editor -> history visible", async ({
  page,
  request,
}) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const bulk = await request.post(
    `${state.backendUrl}/api/projects/${projectId}/chapters/bulk_create`,
    {
      data: {
        chapters: [
          { number: 1, title: "Chapter 1", plan: "Plan 1" },
          { number: 2, title: "Chapter 2", plan: "Plan 2" },
          { number: 3, title: "Chapter 3", plan: "Plan 3" },
        ],
      },
    },
  );
  expect(bulk.ok()).toBeTruthy();
  const bulkJson = (await bulk.json()) as {
    ok: boolean;
    data: { chapters: Array<{ id: string; number: number }> };
  };
  const chapter1 = bulkJson.data.chapters.find(
    (chapter) => chapter.number === 1,
  );
  expect(chapter1?.id).toBeTruthy();

  const seedText = "__SEED_CH1__";
  const seed = await request.put(
    `${state.backendUrl}/api/chapters/${chapter1!.id}`,
    {
      data: { content_md: seedText },
    },
  );
  expect(seed.ok()).toBeTruthy();

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapter1!.id}`);
  const openBatch = page.getByLabel(
    "Open batch generation (writing_open_batch_generation)",
    { exact: true },
  );
  await expect(openBatch).toBeVisible();
  await openBatch.click();

  const modal = page.getByRole("dialog", {
    name: "Batch Generation",
    exact: true,
  });
  await expect(modal).toBeVisible();

  await page.getByRole("spinbutton").fill("1");
  await page
    .getByRole("button", { name: "Start batch generation", exact: true })
    .click();

  const modalSummary = page.getByLabel("batch_generation_runtime_summary", {
    exact: true,
  });
  await expect(modalSummary).toContainText(/queued|running|succeeded/, {
    timeout: 60_000,
  });

  const apply = page
    .getByRole("button", { name: "Apply to editor", exact: true })
    .first();
  await expect(apply).toBeVisible({ timeout: 60_000 });
  await apply.click();

  const applyConfirm = page.getByRole("dialog").filter({
    hasText: "章节有未保存修改，是否应用生成记录？",
  });
  await expect(applyConfirm).toBeVisible({ timeout: 60_000 });
  await applyConfirm
    .getByRole("button", { name: "直接应用（不保存）", exact: true })
    .click();

  await expect(modalSummary).toBeHidden({ timeout: 60_000 });

  const content = page.locator('textarea[name="content_md"]:visible');
  await expect(content).toHaveValue(/E2E/, { timeout: 60_000 });
  await expect(content).not.toHaveValue(new RegExp(seedText));

  const openHistory = page.getByLabel(
    "Open generation history (writing_open_generation_history)",
    { exact: true },
  );
  await openHistory.click({ timeout: 60_000 });

  const drawer = page.locator('[role="dialog"]').last();

  const firstRun = drawer.locator("button").filter({ hasText: "ok" }).first();
  await expect(firstRun).toBeVisible({ timeout: 60_000 });
  await firstRun.click();
  await expect(drawer.getByText("output / error")).toBeVisible();
});
