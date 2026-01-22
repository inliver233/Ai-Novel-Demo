import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: writing generate shows validation error toast and keeps editor content", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as { ok: boolean; data: { chapter: { id: string } } };
  const chapterId = createJson.data.chapter.id;

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);
  const content = page.locator('textarea[name="content_md"]');
  await expect(content).toBeVisible();

  const dirtyMarker = "E2E_VALIDATION_SHOULD_KEEP";
  await content.fill(dirtyMarker);

  await page.getByRole("button", { name: "AI 生成", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "AI 生成", exact: true });
  await expect(drawer).toBeVisible();
  await drawer.getByRole("button", { name: "高级参数", exact: true }).click();
  await drawer.getByRole("checkbox", { name: "流式生成（beta）", exact: true }).uncheck();

  await page.route(`**/api/chapters/${chapterId}/generate`, async (route) => {
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({
        ok: false,
        error: { code: "VALIDATION_ERROR", message: "参数错误", details: { field: "instruction" } },
        request_id: "e2e-request",
      }),
    });
  });

  const genRespP = page.waitForResponse(
    (resp) => resp.request().method() === "POST" && resp.url().endsWith(`/api/chapters/${chapterId}/generate`),
  );

  await drawer.getByRole("button", { name: "生成", exact: true }).click();
  const confirm = page.getByRole("dialog", { name: "章节有未保存修改，如何生成？", exact: true });
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", { name: /直接生成/ }).click();
  const resp = await genRespP;
  expect(resp.status()).toBe(400);

  await expect(page.getByText(/VALIDATION_ERROR/)).toBeVisible();
  await expect(content).toHaveValue(new RegExp(dirtyMarker));
});
