import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: chapter reader shows memory hits and can jump to writing", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    // Avoid auto plot_auto_update (runs async in inline queue and can overwrite manual analysis/apply expectations).
    data: { number: 1, title: "E2E Reader Chapter", plan: "E2E plan", status: "drafting" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as { ok: boolean; data: { chapter: { id: string } } };
  const chapterId = createJson.data.chapter.id;

  const contentMd = `# E2E Chapter 1\n\nE2E_DRAGON appears here.\n\nE2E_FORESHADOW appears here.`;
  const put = await request.put(`${state.backendUrl}/api/chapters/${chapterId}`, {
    data: { content_md: contentMd, status: "drafting" },
  });
  expect(put.ok()).toBeTruthy();

  const apply = await request.post(`${state.backendUrl}/api/chapters/${chapterId}/analysis/apply`, {
    data: {
      draft_content_md: contentMd,
      analysis: {
        schema_version: 1,
        chapter_summary: "E2E summary",
        hooks: [{ excerpt: "E2E_DRAGON", note: "E2E_DRAGON hook note" }],
        foreshadows: [{ excerpt: "E2E_FORESHADOW", note: "E2E_FORESHADOW note", type: "open" }],
        plot_points: [],
        character_states: [],
        suggestions: [],
        overall_notes: "",
      },
    },
  });
  expect(apply.ok()).toBeTruthy();

  await page.goto(`/projects/${projectId}/reader?chapterId=${chapterId}`);

  await expect(page.getByText("正在阅读：第 1 章", { exact: true })).toBeVisible();
  await expect(page.getByText("E2E_DRAGON appears here.")).toBeVisible();

  // Memory sidebar (xl) should show story_memory + foreshadow hits.
  await expect(page.getByText("剧情记忆（story_memory）", { exact: true })).toBeVisible();
  await expect(page.getByText("E2E_DRAGON hook note")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("未回收伏笔（foreshadow_open_loops）", { exact: true })).toBeVisible();
  await expect(page.getByText("E2E_FORESHADOW note").first()).toBeVisible({ timeout: 60_000 });

  await page.getByRole("button", { name: /E2E_DRAGON/, exact: false }).first().click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/writing\\?chapterId=${chapterId}$`));
  await expect(page.getByRole("button", { name: "AI 生成" })).toBeVisible();
});
