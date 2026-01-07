import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

test("ui: outline stream failure falls back to non-stream", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  await page.goto(`/projects/${projectId}/outline`);
  await page.getByRole("button", { name: "AI 生成大纲", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "AI 生成大纲" })).toBeVisible();

  await page.getByRole("checkbox", { name: "流式生成（beta）" }).check();

  let sawStreamCall = false;
  await page.route(`**/api/projects/${projectId}/outline/generate-stream`, async (route) => {
    sawStreamCall = true;
    await route.fulfill({
      status: 500,
      contentType: "text/plain",
      body: "e2e forced stream failure",
    });
  });

  const nonStream = page.waitForResponse((resp) => {
    const url = resp.url();
    return resp.request().method() === "POST" && url.endsWith(`/api/projects/${projectId}/outline/generate`);
  });

  await page.getByRole("button", { name: "生成", exact: true }).click();

  await nonStream;
  expect(sawStreamCall).toBe(true);

  await expect(page.getByText("生成结果预览")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/解析章节：\s*3/)).toBeVisible();
});
