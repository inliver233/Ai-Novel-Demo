import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: prompts test connection works and stays local", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  await page.goto(`/projects/${projectId}/prompts`);
  await expect(page.getByRole("heading", { name: "模型配置", exact: true })).toBeVisible();

  // Should already be bound to the mock openai-compatible profile from bootstrap.
  await expect(page.locator('select[name="provider"]')).toHaveValue("openai_compatible");
  await expect(page.locator('input[name="base_url"]')).toHaveValue(state.mockLlmBaseUrl);

  const testResp = page.waitForResponse(
    (resp) => resp.request().method() === "POST" && resp.url().endsWith("/api/llm/test"),
  );

  await page.getByRole("button", { name: "测试连接", exact: true }).click();

  const resp = await testResp;
  expect(resp.ok()).toBeTruthy();

  const reqBody = resp.request().postDataJSON() as { provider?: string; base_url?: string | null };
  expect(reqBody.provider).toBe("openai_compatible");
  expect(reqBody.base_url).toBe(state.mockLlmBaseUrl);

  const json = (await resp.json()) as { ok: boolean; data?: { text?: string } };
  expect(json.ok).toBe(true);
  expect((json.data?.text ?? "").trim()).toBe("E2E mock response.");

  await expect(page.getByText(/连接成功/)).toBeVisible();
});
