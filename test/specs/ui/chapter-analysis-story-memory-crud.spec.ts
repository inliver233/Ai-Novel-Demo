import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("ui: chapter analysis StoryMemory CRUD + locate", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E StoryMemory CRUD", plan: "用于 ChapterAnalysis StoryMemory CRUD 回归" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as ApiOk<{ chapter: { id: string } }>;
  const chapterId = createJson.data.chapter.id;

  const contentMd = "0123456789ABCDE--E2E-END";
  const update = await request.put(`${state.backendUrl}/api/chapters/${chapterId}`, { data: { content_md: contentMd } });
  expect(update.ok()).toBeTruthy();

  await page.goto(`/projects/${projectId}/chapter-analysis?chapterId=${chapterId}`);
  await expect(page.getByText("章节标注回溯", { exact: true })).toBeVisible();
  await expect(page.getByLabel("story_memory_sidebar", { exact: true })).toBeVisible();

  await page.getByLabel("story_memory_create", { exact: true }).click();
  const createDrawer = page.getByRole("dialog", { name: "新增剧情记忆", exact: true });
  await expect(createDrawer).toBeVisible();

  const title = "E2E StoryMemory 001";
  await createDrawer.getByLabel("story_memory_type", { exact: true }).selectOption("plot_point");
  await createDrawer.getByLabel("story_memory_title", { exact: true }).fill(title);
  await createDrawer.getByLabel("story_memory_content", { exact: true }).fill("E2E_CONTENT_1");
  await createDrawer.getByLabel("story_memory_tags", { exact: true }).fill("tag-a\ntag-b");
  await createDrawer.getByLabel("story_memory_importance", { exact: true }).fill("0.6");
  await createDrawer.getByLabel("story_memory_position", { exact: true }).fill("10");
  await createDrawer.getByLabel("story_memory_length", { exact: true }).fill("5");

  const [createResp] = await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === "POST" &&
        r.url().includes(`/api/projects/${projectId}/story_memories`) &&
        r.status() === 200,
    ),
    createDrawer.getByLabel("story_memory_save", { exact: true }).click(),
  ]);
  const createPayload = (await createResp.json()) as ApiOk<{ story_memory: { id: string } }>;
  expect(createPayload.ok).toBeTruthy();
  const storyMemoryId = createPayload.data.story_memory.id;

  await expect(createDrawer).toBeHidden({ timeout: 60_000 });
  await expect(page.getByLabel(`story_memory_item:${title}`, { exact: true })).toBeVisible({ timeout: 60_000 });

  await page.getByLabel(`story_memory_item:${title}`, { exact: true }).click();

  const highlight = page.locator(`[data-annotation-id="${storyMemoryId}"]`).first();
  await expect(highlight).toBeVisible();
  await expect(highlight).toHaveClass(/bg-success\/10/);

  await page.getByLabel("story_memory_edit", { exact: true }).click();
  const editDrawer = page.getByRole("dialog", { name: "编辑剧情记忆", exact: true });
  await expect(editDrawer).toBeVisible();

  const updatedContent = "E2E_CONTENT_2 updated";
  await editDrawer.getByLabel("story_memory_content", { exact: true }).fill(updatedContent);

  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.request().method() === "PUT" &&
        r.url().includes(`/api/projects/${projectId}/story_memories/${encodeURIComponent(storyMemoryId)}`) &&
        r.status() === 200,
    ),
    editDrawer.getByLabel("story_memory_save", { exact: true }).click(),
  ]);
  await expect(editDrawer).toBeHidden({ timeout: 60_000 });

  await page.getByLabel("story_memory_edit", { exact: true }).click();
  await expect(editDrawer).toBeVisible();
  await expect(editDrawer.getByLabel("story_memory_content", { exact: true })).toHaveValue(updatedContent);
  await editDrawer.getByLabel("story_memory_close", { exact: true }).click();
  await expect(editDrawer).toBeHidden();

  await page.getByLabel("story_memory_delete", { exact: true }).click();
  const confirmDelete = page.getByRole("dialog", { name: "删除该条剧情记忆？", exact: true });
  await expect(confirmDelete).toBeVisible();
  await confirmDelete.getByRole("button", { name: "删除", exact: true }).click();
  await expect(confirmDelete).toBeHidden({ timeout: 60_000 });

  await expect(page.getByLabel(`story_memory_item:${title}`, { exact: true })).toHaveCount(0);
  await expect(page.locator(`[data-annotation-id="${storyMemoryId}"]`)).toHaveCount(0);
});
