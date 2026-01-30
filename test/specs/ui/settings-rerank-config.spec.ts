import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("ui: settings rerank api_key saves and only masked is shown", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const expandDetails = async (title: string) => {
    const summary = page.locator("summary", { hasText: title });
    await expect(summary).toBeVisible();
    const details = summary.locator("..");
    if ((await details.getAttribute("open")) === null) {
      await summary.click();
      await expect(details).toHaveAttribute("open", "");
    }
  };

  await page.goto(`/projects/${projectId}/settings`);
  await expect(page.getByText("项目信息", { exact: true })).toBeVisible();

  await expandDetails("向量检索（Vector RAG）");
  await expandDetails("Rerank 提供方配置");

  const rawKey = "rk-test-1234";
  const keyInput = page.getByLabel("settings_vector_rerank_api_key", { exact: true });
  await expect(keyInput).toBeVisible();
  await keyInput.fill(rawKey);

  const save = page.getByRole("button", { name: "保存", exact: true });
  await expect(save).toBeEnabled();
  const putResPromise = page.waitForResponse(
    (resp) => resp.request().method() === "PUT" && resp.url().includes(`/api/projects/${projectId}/settings`) && resp.ok(),
  );
  const [putRes] = await Promise.all([putResPromise, save.click()]);
  await expect(save).toBeDisabled();

  const putJson = (await putRes.json()) as ApiOk<{ settings: Record<string, unknown> }>;
  const putSettings = putJson.data.settings as {
    vector_rerank_has_api_key: boolean;
    vector_rerank_masked_api_key: string;
    vector_rerank_api_key?: unknown;
  };
  expect(putSettings.vector_rerank_has_api_key).toBe(true);
  expect(putSettings.vector_rerank_masked_api_key).toBeTruthy();
  expect(putSettings.vector_rerank_masked_api_key).not.toContain(rawKey);
  expect(putSettings.vector_rerank_api_key).toBeUndefined();

  const settingsRes = await request.get(`${state.backendUrl}/api/projects/${projectId}/settings`);
  expect(settingsRes.ok()).toBeTruthy();
  const settingsJson = (await settingsRes.json()) as ApiOk<{ settings: Record<string, unknown> }>;
  const settings = settingsJson.data.settings as {
    vector_rerank_has_api_key: boolean;
    vector_rerank_masked_api_key: string;
    vector_rerank_api_key?: unknown;
  };

  expect(settings.vector_rerank_has_api_key).toBe(true);
  expect(settings.vector_rerank_masked_api_key).toBeTruthy();
  expect(settings.vector_rerank_masked_api_key).not.toContain(rawKey);
  expect(settings.vector_rerank_api_key).toBeUndefined();

  await expandDetails("向量检索（Vector RAG）");
  await expandDetails("Rerank 提供方配置");

  await expect(keyInput).toHaveValue("");
  await expect(keyInput.locator("..")).toContainText("****");
  await expect(keyInput.locator("..")).not.toContainText(rawKey);
  await expect(page.getByText(rawKey, { exact: false })).toHaveCount(0);
});

