import { test, expect } from "@playwright/test";

import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };
type ApiErr = { ok: false; error: { code: string; message: string; details?: unknown }; request_id: string };

test("api: outline generate returns LLM_CONFIG_ERROR when preset missing", async ({ request }) => {
  const state = loadState();

  // Create a project without binding llm_profile_id, so LLMPreset row is missing.
  const projectRes = await request.post(`${state.backendUrl}/api/projects`, {
    data: { name: "E2E Outline Missing Preset", genre: "Test", logline: "outline preset missing contract" },
  });
  expect(projectRes.ok()).toBeTruthy();
  const projectJson = (await projectRes.json()) as ApiOk<{ project: { id: string } }>;
  const projectId = projectJson.data.project.id;

  const gen = await request.post(`${state.backendUrl}/api/projects/${projectId}/outline/generate`, {
    data: {},
  });
  expect(gen.status()).toBe(400);
  const genJson = (await gen.json()) as ApiErr;
  expect(genJson.ok).toBe(false);
  expect(genJson.error.code).toBe("LLM_CONFIG_ERROR");
  expect(genJson.error.message).toBe("请先在 Prompts 页保存 LLM 配置");
});

