import { test, expect } from "../../lib/ui-test";

import type { Page } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

async function createStoryMemoryViaUi(args: {
  projectId: string;
  title: string;
  content: string;
  position: string;
  length: string;
  page: Page;
}) {
  const { page, projectId, title, content, position, length } = args;

  await page.getByLabel("story_memory_create", { exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "新增剧情记忆", exact: true });
  await expect(drawer).toBeVisible();

  await drawer.getByLabel("story_memory_type", { exact: true }).selectOption("plot_point");
  await drawer.getByLabel("story_memory_title", { exact: true }).fill(title);
  await drawer.getByLabel("story_memory_content", { exact: true }).fill(content);
  await drawer.getByLabel("story_memory_importance", { exact: true }).fill("0.6");
  await drawer.getByLabel("story_memory_position", { exact: true }).fill(position);
  await drawer.getByLabel("story_memory_length", { exact: true }).fill(length);

  const [createResp] = await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === "POST" &&
        r.url().includes(`/api/projects/${projectId}/story_memories`) &&
        r.status() === 200,
    ),
    drawer.getByLabel("story_memory_save", { exact: true }).click(),
  ]);
  const createPayload = (await createResp.json()) as ApiOk<{ story_memory: { id: string } }>;
  expect(createPayload.ok).toBeTruthy();

  await expect(drawer).toBeHidden({ timeout: 60_000 });
  return createPayload.data.story_memory.id;
}

test("ui: chapter analysis StoryMemory merge removes sources + highlights", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E StoryMemory Merge", plan: "用于 ChapterAnalysis StoryMemory 合并回归" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as ApiOk<{ chapter: { id: string } }>;
  const chapterId = createJson.data.chapter.id;

  const contentMd = "0123456789ABCDE--E2E-MERGE-END";
  const update = await request.put(`${state.backendUrl}/api/chapters/${chapterId}`, { data: { content_md: contentMd } });
  expect(update.ok()).toBeTruthy();

  await page.goto(`/projects/${projectId}/chapter-analysis?chapterId=${chapterId}`);
  await expect(page.getByText("章节标注回溯", { exact: true })).toBeVisible();
  await expect(page.getByLabel("story_memory_sidebar", { exact: true })).toBeVisible();

  const titleTarget = "E2E Merge Target";
  const idTarget = await createStoryMemoryViaUi({
    projectId,
    title: titleTarget,
    content: "E2E_CONTENT_TARGET",
    position: "2",
    length: "4",
    page,
  });

  const titleSource = "E2E Merge Source";
  const idSource = await createStoryMemoryViaUi({
    projectId,
    title: titleSource,
    content: "E2E_CONTENT_SOURCE",
    position: "10",
    length: "5",
    page,
  });

  await expect(page.getByLabel(`story_memory_item:${titleTarget}`, { exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByLabel(`story_memory_item:${titleSource}`, { exact: true })).toBeVisible({ timeout: 60_000 });

  await page.getByLabel(`story_memory_item:${titleTarget}`, { exact: true }).click();
  await expect(page.locator(`[data-annotation-id="${idTarget}"]`).first()).toBeVisible();
  await expect(page.locator(`[data-annotation-id="${idSource}"]`).first()).toBeVisible();

  await page.getByLabel("story_memory_merge", { exact: true }).click();
  const mergeDrawer = page.getByRole("dialog", { name: "合并剧情记忆", exact: true });
  await expect(mergeDrawer).toBeVisible();

  await mergeDrawer.getByLabel(`story_memory_merge_source:${titleSource}`, { exact: true }).check();

  const mergeRespP = page.waitForResponse(
    (r) =>
      r.request().method() === "POST" &&
      r.url().includes(`/api/projects/${projectId}/story_memories/merge`) &&
      r.status() === 200,
  );
  await mergeDrawer.getByLabel("story_memory_merge_apply", { exact: true }).click();

  const confirm = page.getByRole("dialog", { name: "确认合并？", exact: true });
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", { name: "合并", exact: true }).click();

  await mergeRespP;
  await expect(confirm).toBeHidden({ timeout: 60_000 });
  await expect(mergeDrawer).toBeHidden({ timeout: 60_000 });

  await expect(page.getByLabel(`story_memory_item:${titleSource}`, { exact: true })).toHaveCount(0);
  await expect(page.locator(`[data-annotation-id="${idSource}"]`)).toHaveCount(0);
  await expect(page.locator(`[data-annotation-id="${idTarget}"]`).first()).toBeVisible();
});
