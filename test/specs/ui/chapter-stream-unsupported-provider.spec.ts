import { test, expect } from "../../lib/ui-test";

import { bootstrapProjectWithLlmProfile } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: stream enabled with non-openai provider shows downgrade notice", async ({ page, request }) => {
  const state = loadState();
  const mockHostBaseUrl = state.mockLlmBaseUrl.endsWith("/v1") ? state.mockLlmBaseUrl.slice(0, -3) : state.mockLlmBaseUrl;

  const { projectId } = await bootstrapProjectWithLlmProfile(request, {
    name: "e2e-mock-anthropic",
    provider: "anthropic",
    base_url: mockHostBaseUrl,
    model: "claude-mock",
    api_key: "test-key",
  });

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as { ok: boolean; data: { chapter: { id: string } } };
  const chapterId = createJson.data.chapter.id;

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);
  const content = page.locator('textarea[name="content_md"]');
  await expect(content).toHaveValue("");

  await page.getByRole("button", { name: "AI 生成", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "AI 生成", exact: true });
  await expect(drawer).toBeVisible();

  await drawer.getByRole("button", { name: "高级参数", exact: true }).click();
  await drawer.getByRole("checkbox", { name: "流式生成（beta）", exact: true }).check();
  await drawer.locator('textarea[name="instruction"]').fill("E2E_PROVIDER_UNSUPPORTED <<<CONTENT");

  await drawer.getByRole("button", { name: "生成", exact: true }).click();

  await expect(content).not.toHaveValue("", { timeout: 30_000 });
  await expect(content).toContainText("E2E");

  await expect(page.getByText(/不支持流式/)).toBeVisible();
});
