import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("api: health + basic CRUD", async ({ request }) => {
  const state = loadState();

  const health = await request.get(`${state.backendUrl}/api/health`);
  expect(health.ok()).toBeTruthy();
  const healthJson = (await health.json()) as { ok: boolean; data?: { status?: string } };
  expect(healthJson.ok).toBe(true);
  expect(healthJson.data?.status).toBe("healthy");

  const { projectId } = await bootstrapProject(request);

  const listProjects = await request.get(`${state.backendUrl}/api/projects`);
  expect(listProjects.ok()).toBeTruthy();
  const listJson = (await listProjects.json()) as { ok: boolean; data: { projects: Array<{ id: string }> } };
  expect(listJson.ok).toBe(true);
  expect(listJson.data.projects.some((p) => p.id === projectId)).toBe(true);

  const settings = await request.get(`${state.backendUrl}/api/projects/${projectId}/settings`);
  expect(settings.ok()).toBeTruthy();

  const putSettings = await request.put(`${state.backendUrl}/api/projects/${projectId}/settings`, {
    data: { world_setting: "E2E world", style_guide: "E2E style", constraints: "E2E constraints" },
  });
  expect(putSettings.ok()).toBeTruthy();

  const createChar = await request.post(`${state.backendUrl}/api/projects/${projectId}/characters`, {
    data: { name: "Alice", role: "Protagonist", profile: "Brave", notes: "E2E character" },
  });
  expect(createChar.ok()).toBeTruthy();
  const charJson = (await createChar.json()) as { ok: boolean; data: { character: { id: string; name: string } } };
  expect(charJson.ok).toBe(true);
  expect(charJson.data.character.name).toBe("Alice");

  const listChars = await request.get(`${state.backendUrl}/api/projects/${projectId}/characters`);
  expect(listChars.ok()).toBeTruthy();

  const exportMd = await request.get(`${state.backendUrl}/api/projects/${projectId}/export/markdown`);
  // Export may require outline/chapters; allow either a success markdown or a structured API error payload.
  const ct = exportMd.headers()["content-type"] ?? "";
  if (exportMd.ok() && ct.includes("text/markdown")) {
    const text = await exportMd.text();
    expect(text.length).toBeGreaterThan(0);
  } else {
    const payload = (await exportMd.json()) as { ok: boolean; error?: { code?: string } };
    expect(payload.ok).toBe(false);
    expect(typeof payload.error?.code).toBe("string");
  }
});

test("api: error when llm api key missing", async ({ request }) => {
  const state = loadState();
  const { projectId, profileId } = await bootstrapProject(request);

  const cleared = await request.put(`${state.backendUrl}/api/llm_profiles/${profileId}`, { data: { api_key: "" } });
  expect(cleared.ok()).toBeTruthy();

  const res = await request.post(`${state.backendUrl}/api/projects/${projectId}/outline/generate`, {
    headers: { "X-LLM-Provider": "openai_compatible" },
    data: {
      requirements: { chapter_count: 2 },
      context: { include_world_setting: false, include_characters: false },
    },
  });
  expect(res.status()).toBe(401);
  const json = (await res.json()) as { ok: boolean; error?: { code?: string } };
  expect(json.ok).toBe(false);
  expect(json.error?.code).toBe("LLM_KEY_MISSING");
});

test("api: chapter bulk_create conflict + duplicate validation", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const first = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters/bulk_create`, {
    data: { chapters: [{ number: 1, title: "c1", plan: "" }] },
  });
  expect(first.ok()).toBeTruthy();

  const conflict = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters/bulk_create`, {
    data: { chapters: [{ number: 1, title: "c1-again", plan: "" }] },
  });
  expect(conflict.status()).toBe(409);
  const conflictJson = (await conflict.json()) as { ok: boolean; error?: { code?: string } };
  expect(conflictJson.ok).toBe(false);
  expect(conflictJson.error?.code).toBe("CONFLICT");

  const dup = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters/bulk_create?replace=1`, {
    data: { chapters: [{ number: 1, title: "a", plan: "" }, { number: 1, title: "b", plan: "" }] },
  });
  expect(dup.status()).toBe(400);
  const dupJson = (await dup.json()) as { ok: boolean; error?: { code?: string } };
  expect(dupJson.ok).toBe(false);
  expect(dupJson.error?.code).toBe("VALIDATION_ERROR");
});
