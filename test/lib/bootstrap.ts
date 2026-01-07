import type { APIRequestContext } from "@playwright/test";

import { loadState } from "./state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

export type BootstrapLlmProfile = {
  name: string;
  provider: string;
  base_url: string;
  model: string;
  api_key: string;
  extra?: Record<string, unknown> | null;
};

export async function bootstrapProjectWithLlmProfile(
  request: APIRequestContext,
  llmProfile: BootstrapLlmProfile,
): Promise<{
  projectId: string;
  profileId: string;
}> {
  const state = loadState();
  const profileRes = await request.post(`${state.backendUrl}/api/llm_profiles`, {
    data: llmProfile,
  });
  if (!profileRes.ok()) throw new Error(`Failed to create llm profile: ${profileRes.status()} ${await profileRes.text()}`);
  const profileJson = (await profileRes.json()) as ApiOk<{ profile: { id: string } }>;
  const profileId = profileJson.data.profile.id;

  const projectRes = await request.post(`${state.backendUrl}/api/projects`, {
    data: { name: "E2E Project", genre: "Test", logline: "E2E automated test project" },
  });
  if (!projectRes.ok()) throw new Error(`Failed to create project: ${projectRes.status()} ${await projectRes.text()}`);
  const projectJson = (await projectRes.json()) as ApiOk<{ project: { id: string } }>;
  const projectId = projectJson.data.project.id;

  const bindRes = await request.put(`${state.backendUrl}/api/projects/${projectId}`, {
    data: { llm_profile_id: profileId },
  });
  if (!bindRes.ok()) throw new Error(`Failed to bind profile: ${bindRes.status()} ${await bindRes.text()}`);

  // Ensure the preset row exists and is synced (used by UI headers and generation routes).
  const presetRes = await request.get(`${state.backendUrl}/api/projects/${projectId}/llm_preset`);
  if (!presetRes.ok()) throw new Error(`Failed to read llm_preset: ${presetRes.status()} ${await presetRes.text()}`);

  return { projectId, profileId };
}

export async function bootstrapProject(request: APIRequestContext): Promise<{
  projectId: string;
  profileId: string;
}> {
  const state = loadState();
  return bootstrapProjectWithLlmProfile(request, {
    name: "e2e-mock-openai-compatible",
    provider: "openai_compatible",
    base_url: state.mockLlmBaseUrl,
    model: "gpt-4o-mini",
    api_key: "test-key",
  });
}
