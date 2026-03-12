import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("ui: content_optimize without stream checkbox still uses reliable stream transport", async ({ page, request }) => {
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
  await expect(page.getByText("已为规划/润色/正文优化自动启用可靠链路，避免请求超时。")).toBeVisible();

  let sawNonStreamGenerate = false;
  await page.route(`**/api/chapters/${chapterId}/generate`, async (route) => {
    sawNonStreamGenerate = true;
    await route.fallback();
  });
  const genReqP = page.waitForRequest(
    (req) => req.method() === "POST" && req.url().endsWith(`/api/chapters/${chapterId}/generate-stream`),
  );
  await drawer.getByRole("button", { name: "生成", exact: true }).click();
  await genReqP;
  await expect(page.locator('textarea[name="content_md"]')).not.toHaveValue("", { timeout: 60_000 });
  expect(sawNonStreamGenerate).toBe(false);

  const contentOptimizeCompareButton = drawer.getByRole("button", { name: "正文优化对比/回退", exact: true });
  await expect(contentOptimizeCompareButton).toBeVisible({ timeout: 60_000 });
  await contentOptimizeCompareButton.click();
  const compare = page.getByRole("dialog", { name: "正文优化对比", exact: true });
  await expect(compare).toBeVisible();
  await compare.getByRole("button", { name: "优化稿", exact: true }).click();
  await expect(compare).toContainText("E2E 正文优化校验已完成");
  await compare.getByRole("button", { name: "关闭", exact: true }).click();

  await drawer.getByRole("button", { name: "关闭", exact: true }).click();
  const openHistory = page.getByLabel("Open generation history (writing_open_generation_history)", { exact: true });
  await expect(openHistory).toBeVisible({ timeout: 60_000 });
  await openHistory.click();
  const history = page.getByRole("dialog", { name: "生成记录", exact: true });
  await expect(history).toBeVisible();

  const contentOptimizePipelineButton = history.locator('button[aria-label^="pipeline run_id:"]').filter({
    hasText: "content_optimize",
  });
  await expect(contentOptimizePipelineButton).toHaveCount(1, { timeout: 60_000 });
  await contentOptimizePipelineButton.first().click();
  await expect(history).toContainText('"content_optimize": true');
});
