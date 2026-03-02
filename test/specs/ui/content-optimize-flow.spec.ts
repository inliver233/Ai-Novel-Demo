import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("ui: content_optimize toggle sends payload and exposes compare entry when diff exists", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as ApiOk<{ chapter: { id: string } }>;
  const chapterId = createJson.data.chapter.id;

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);
  await page.getByRole("button", { name: "AI 生成", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "AI 生成", exact: true });
  await expect(drawer).toBeVisible();

  await drawer.getByRole("button", { name: "高级参数", exact: true }).click();
  await drawer.getByRole("checkbox", { name: "流式生成（beta）", exact: true }).uncheck();
  await drawer.getByRole("checkbox", { name: "正文优化", exact: true }).check();

  const genRespP = page.waitForResponse(
    (resp) => resp.request().method() === "POST" && resp.url().endsWith(`/api/chapters/${chapterId}/generate`),
  );
  await drawer.getByRole("button", { name: "生成", exact: true }).click();
  const genResp = await genRespP;
  expect(genResp.ok()).toBeTruthy();

  const genJson = (await genResp.json()) as ApiOk<{
    content_optimize_applied?: boolean;
    content_optimize_raw_content_md?: string;
    content_optimize_optimized_content_md?: string;
    content_optimize_run_id?: string;
  }>;
  const raw = (genJson.data.content_optimize_raw_content_md ?? "").trim();
  const optimized = (genJson.data.content_optimize_optimized_content_md ?? "").trim();

  expect(typeof genJson.data.content_optimize_applied).toBe("boolean");
  expect(typeof genJson.data.content_optimize_run_id).toBe("string");
  expect(raw.length).toBeGreaterThan(0);

  const compareButton = drawer.getByRole("button", { name: "正文优化对比/回退", exact: true });
  if (optimized.length > 0 && raw !== optimized) {
    await expect(compareButton).toBeVisible();
    await compareButton.click();
    await expect(page.getByRole("dialog", { name: "正文优化对比", exact: true })).toBeVisible();
  } else {
    await expect(compareButton).toHaveCount(0);
  }
});
