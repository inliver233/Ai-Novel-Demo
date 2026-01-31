import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: chapter analysis annotated text groups overlap + adjacency; click selects primary", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 标注聚合", plan: "用于 AnnotatedText 聚合回归" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as { ok: boolean; data: { chapter: { id: string } } };
  const chapterId = createJson.data.chapter.id;

  const contentMd = "ABCDEFGH------------IJKL++MNOPQR";
  const update = await request.put(`${state.backendUrl}/api/chapters/${chapterId}`, {
    data: { content_md: contentMd },
  });
  expect(update.ok()).toBeTruthy();

  const apply = await request.post(`${state.backendUrl}/api/chapters/${chapterId}/analysis/apply`, {
    data: {
      analysis: {
        chapter_summary: "E2E_SUMMARY_NOT_IN_TEXT_12345",
        hooks: [{ excerpt: "BCDE", note: "Hook BCDE" }, { excerpt: "IJKL", note: "Hook IJKL" }],
        foreshadows: [
          { excerpt: "CDEF", note: "Foreshadow CDEF", type: "open" },
          { excerpt: "MNOP", note: "Foreshadow MNOP", type: "open" },
        ],
      },
    },
  });
  expect(apply.ok()).toBeTruthy();

  await page.goto(`/projects/${projectId}/chapter-analysis?chapterId=${chapterId}`);
  await expect(page.getByText("章节标注回溯", { exact: true })).toBeVisible();
  await expect(page.getByLabel("story_memory_sidebar", { exact: true })).toBeVisible();

  const highlights = page.locator("[data-annotation-id]");
  await expect.poll(async () => await highlights.count(), { timeout: 60_000 }).toBeGreaterThan(0);

  const overlap = highlights.filter({ hasText: "CDE" }).first();
  await expect(overlap).toBeVisible();
  const overlapTitle = (await overlap.getAttribute("title")) ?? "";
  expect(overlapTitle).toContain("BCDE");
  expect(overlapTitle).toContain("CDEF");

  await overlap.click();
  await expect(overlap).toHaveClass(/bg-info\/10/);

  const gap = highlights.filter({ hasText: "++" }).first();
  await expect(gap).toBeVisible();
  const gapTitle = (await gap.getAttribute("title")) ?? "";
  expect(gapTitle).toContain("IJKL");
  expect(gapTitle).toContain("MNOP");

  const mnop = highlights.filter({ hasText: "MNOP" }).first();
  await gap.click();
  await expect(mnop).toHaveClass(/bg-info\/10/);
});
