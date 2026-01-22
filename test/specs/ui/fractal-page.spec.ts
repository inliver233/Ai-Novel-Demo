import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

test("ui: FractalPage loads and rebuild controls are available", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  const initialLoadResponse = page.waitForResponse(
    (resp) => resp.url().includes(`/api/projects/${projectId}/fractal`) && resp.request().method() === "GET" && resp.ok(),
  );
  await page.goto(`/projects/${projectId}/fractal`);

  await expect(page.getByText("分形记忆（Fractal）", { exact: true })).toBeVisible();
  await initialLoadResponse;

  const refreshButton = page.getByRole("button", { name: "刷新", exact: true });
  await expect(refreshButton).toBeEnabled();

  const refreshResponse = page.waitForResponse(
    (resp) => resp.url().includes(`/api/projects/${projectId}/fractal`) && resp.request().method() === "GET" && resp.ok(),
  );
  await refreshButton.click();
  await refreshResponse;

  const rebuildDeterministicButton = page.getByRole("button", { name: "重建（确定性）", exact: true });
  await expect(rebuildDeterministicButton).toBeEnabled();

  const rebuildDeterministicResponse = page.waitForResponse(
    (resp) =>
      resp.url().includes(`/api/projects/${projectId}/fractal/rebuild`) && resp.request().method() === "POST" && resp.ok(),
  );
  await rebuildDeterministicButton.click();
  await rebuildDeterministicResponse;

  const rebuildV2Button = page.getByRole("button", { name: "重建（LLM 摘要）", exact: true });
  await expect(rebuildV2Button).toBeEnabled();
});
