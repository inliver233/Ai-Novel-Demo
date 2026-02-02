import { test, expect } from "../../lib/ui-test";

import type { APIRequestContext } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

async function createDoneChapter(request: APIRequestContext, projectId: string): Promise<string> {
  const state = loadState();
  const res = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: {
      number: 1,
      title: "E2E 第一章",
      plan: "dragon",
      status: "done",
    },
  });
  if (!res.ok()) throw new Error(`Failed to create chapter: ${res.status()} ${await res.text()}`);
  const json = (await res.json()) as ApiOk<{ chapter: { id: string } }>;
  if (!json.ok) throw new Error("Create chapter response not ok");
  return json.data.chapter.id;
}

test("ui: GraphPage manual graph_auto_update task is traceable in TaskCenter", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);
  const chapterId = await createDoneChapter(request, projectId);

  await page.goto(`/projects/${projectId}/graph?chapterId=${encodeURIComponent(chapterId)}`);

  const queryInput = page.getByLabel("graph_query_text", { exact: true });
  await expect(queryInput).toBeVisible();
  await queryInput.fill("dragon");
  await page.getByRole("button", { name: "查询", exact: true }).click();

  const [autoRes] = await Promise.all([
    page.waitForResponse(
      (r) =>
        r.url().includes(`/api/projects/${projectId}/graph/auto_update`) &&
        r.request().method() === "POST" &&
        r.status() === 200,
    ),
    page.getByRole("button", { name: "创建自动更新任务", exact: true }).click(),
  ]);

  const autoJson = (await autoRes.json()) as ApiOk<{ task_id: string }>;
  expect(autoJson.ok).toBeTruthy();
  const taskId = String(autoJson.data.task_id || "").trim();
  expect(taskId).toBeTruthy();

  await expect(page.getByText(taskId, { exact: true })).toBeVisible();
  await page.getByLabel("graph_open_task_center", { exact: true }).click();

  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/tasks`));
  await expect(page.getByText(taskId)).toBeVisible();
});
