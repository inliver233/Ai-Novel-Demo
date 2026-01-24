import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("api: generation_runs records prompt_inspector + export toggle (override redacted)", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as ApiOk<{ chapter: { id: string } }>;
  const chapterId = createJson.data.chapter.id;

  const macroSeed = "e2e-prompt-inspector-seed";
  const overrideKey = "sk-test-1234567890";
  const gen = await request.post(`${state.backendUrl}/api/chapters/${chapterId}/generate`, {
    headers: { "X-LLM-Provider": "openai_compatible" },
    data: {
      mode: "replace",
      instruction: "E2E prompt inspector params",
      target_word_count: 200,
      plan_first: false,
      post_edit: false,
      post_edit_sanitize: false,
      macro_seed: macroSeed,
      prompt_override: {
        system: "SYS override",
        user: `USER override ${overrideKey}`,
      },
      memory_injection_enabled: false,
      context: {
        include_world_setting: false,
        include_style_guide: false,
        include_constraints: false,
        include_outline: false,
        include_smart_context: false,
        require_sequential: false,
        character_ids: [],
        previous_chapter: "none",
      },
    },
  });
  expect(gen.ok()).toBeTruthy();
  const genJson = (await gen.json()) as ApiOk<{ generation_run_id: string }>;
  const runId = genJson.data.generation_run_id;
  expect(typeof runId).toBe("string");
  expect(runId.length).toBeGreaterThan(0);

  const run = await request.get(`${state.backendUrl}/api/generation_runs/${runId}`);
  expect(run.ok()).toBeTruthy();
  const runJson = (await run.json()) as ApiOk<{ run: { params: Record<string, unknown> } }>;
  const params = runJson.data.run.params;
  expect(params).toHaveProperty("prompt_inspector");

  const inspector = params.prompt_inspector as Record<string, unknown>;
  expect(inspector.macro_seed).toBe(macroSeed);
  expect(inspector.prompt_overridden).toBe(true);
  expect(JSON.stringify(inspector)).not.toContain(overrideKey);
  expect(JSON.stringify(inspector)).toContain("sk-***");

  const bundle = await request.get(`${state.backendUrl}/api/generation_runs/${runId}/debug_bundle`);
  expect(bundle.ok()).toBeTruthy();
  const bundleJson = JSON.parse(await bundle.text()) as { params?: Record<string, unknown> };
  expect(bundleJson.params?.prompt_inspector).toBeUndefined();

  const bundleWithPrompt = await request.get(
    `${state.backendUrl}/api/generation_runs/${runId}/debug_bundle?include_prompt_inspector=1`,
  );
  expect(bundleWithPrompt.ok()).toBeTruthy();
  const bundleWithPromptRaw = await bundleWithPrompt.text();
  const bundleWithPromptJson = JSON.parse(bundleWithPromptRaw) as { params?: Record<string, unknown> };
  expect(bundleWithPromptJson.params?.prompt_inspector).toBeTruthy();

  // Must not leak api keys (bootstrapProject uses "test-key").
  expect(bundleWithPromptRaw).not.toContain(overrideKey);
  expect(bundleWithPromptRaw).not.toContain("test-key");
  expect(bundleWithPromptRaw).not.toMatch(/sk-[a-zA-Z0-9]{10,}/);
});

