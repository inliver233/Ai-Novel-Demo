import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: chapter stream failure falls back to non-stream", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "要点 A；要点 B" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as { ok: boolean; data: { chapter: { id: string } } };
  const chapterId = createJson.data.chapter.id;

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);
  const content = page.locator('textarea[name="content_md"]');
  await expect(content).toHaveValue("");

  await page.getByRole("button", { name: "AI 生成" }).click();
  const drawer = page.getByRole("dialog", { name: "AI 生成" });
  await expect(drawer).toBeVisible();

  await drawer.getByRole("button", { name: "高级参数", exact: true }).click();
  await drawer.getByRole("checkbox", { name: "流式生成（beta）", exact: true }).check();

  let sawStreamCall = false;
  await page.route(`**/api/chapters/${chapterId}/generate-stream`, async (route) => {
    sawStreamCall = true;
    await route.fulfill({
      status: 500,
      contentType: "text/plain",
      body: "e2e forced stream failure",
    });
  });

  const nonStream = page.waitForResponse((resp) => {
    const url = resp.url();
    return resp.request().method() === "POST" && url.endsWith(`/api/chapters/${chapterId}/generate`);
  });

  await page.getByRole("button", { name: "生成", exact: true }).click();

  const resp = await nonStream;
  expect(resp.ok()).toBeTruthy();
  expect(sawStreamCall).toBe(true);

  await expect(content).not.toHaveValue("", { timeout: 60_000 });
  await expect(content).toContainText("E2E");
});
