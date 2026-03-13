import { test, expect } from "../../lib/ui-test";

import { bootstrapProject, bootstrapProjectWithLlmProfile } from "../../lib/bootstrap";
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

test("ui: prompts explains blocked model actions when profile key is missing", async ({ page, request }) => {
  const state = loadState();
  const { projectId, profileId } = await bootstrapProjectWithLlmProfile(request, {
    name: "e2e-mock-openai-compatible-no-key",
    provider: "openai_compatible",
    base_url: state.mockLlmBaseUrl,
    model: "gpt-4o-mini",
    api_key: "temp-key",
  });

  const cleared = await request.put(`${state.backendUrl}/api/llm_profiles/${profileId}`, {
    data: { api_key: "" },
  });
  expect(cleared.ok()).toBeTruthy();

  await page.goto(`/projects/${projectId}/prompts`);
  await expect(page.getByRole("heading", { name: "模型配置", exact: true })).toBeVisible();

  await expect(page.getByText("远程状态：已绑定 profile，但未保存 Key", { exact: true })).toHaveCount(1);
  const modelButtons = page.getByRole("button", { name: "拉取模型列表", exact: true });
  const testButtons = page.getByRole("button", { name: "测试连接", exact: true });
  await expect(modelButtons.first()).toBeDisabled();
  await expect(testButtons.first()).toBeDisabled();
  await expect(page.getByText(/保存 Key 后才能拉取模型列表或测试连接/)).toBeVisible();
  await expect(page.getByText(/当前不可拉取模型列表：/)).toBeVisible();

  await page.getByRole("button", { name: "新增模块", exact: true }).click();
  await expect(page.getByText("远程状态：已绑定 profile，但未保存 Key", { exact: true })).toHaveCount(2);
  await expect(modelButtons.nth(1)).toBeDisabled();
  await expect(testButtons.nth(1)).toBeDisabled();
});
