import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: plan_first without stream checkbox still uses reliable stream transport", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "要点 A；要点 B" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as { ok: boolean; data: { chapter: { id: string } } };
  const chapterId = createJson.data.chapter.id;

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);
  await page.getByRole("button", { name: "AI 生成", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "AI 生成", exact: true });
  await expect(drawer).toBeVisible();

  await drawer.getByRole("button", { name: "高级参数", exact: true }).click();
  await drawer.getByRole("checkbox", { name: "流式生成（beta）", exact: true }).uncheck();
  await drawer.getByRole("checkbox", { name: "先生成规划", exact: true }).check();
  await expect(page.getByText("已为规划/润色/正文优化自动启用可靠链路，避免请求超时。")).toBeVisible();

  let sawNonStreamGenerate = false;
  await page.route(`**/api/chapters/${chapterId}/generate`, async (route) => {
    sawNonStreamGenerate = true;
    await route.fallback();
  });
  const streamReqP = page.waitForRequest(
    (req) => req.method() === "POST" && req.url().endsWith(`/api/chapters/${chapterId}/generate-stream`),
  );

  const content = page.locator('textarea[name="content_md"]');
  await drawer.getByRole("button", { name: "生成", exact: true }).click();

  await streamReqP;
  await expect(content).not.toHaveValue("", { timeout: 60_000 });
  await expect(content).toContainText("E2E");
  expect(sawNonStreamGenerate).toBe(false);
});
