import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("api: chapter_generate (non-stream) + generation_runs contract", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as ApiOk<{ chapter: { id: string } }>;
  const chapterId = createJson.data.chapter.id;

  const gen = await request.post(`${state.backendUrl}/api/chapters/${chapterId}/generate`, {
    headers: { "X-LLM-Provider": "openai_compatible" },
    data: {
      mode: "replace",
      instruction: "E2E contract test",
      target_word_count: 300,
      plan_first: false,
      post_edit: false,
      memory_injection_enabled: true,
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

  const genJson = (await gen.json()) as ApiOk<{
    content_md: string;
    summary: string;
    raw_output: string;
    generation_run_id: string;
  }>;
  expect(genJson.ok).toBe(true);
  expect(typeof genJson.request_id).toBe("string");
  expect(typeof genJson.data.content_md).toBe("string");
  expect(genJson.data.content_md.length).toBeGreaterThan(0);
  expect(typeof genJson.data.summary).toBe("string");
  expect(typeof genJson.data.raw_output).toBe("string");
  expect(typeof genJson.data.generation_run_id).toBe("string");
  expect(genJson.data.generation_run_id.length).toBeGreaterThan(0);

  const list = await request.get(`${state.backendUrl}/api/projects/${projectId}/generation_runs?limit=10`);
  expect(list.ok()).toBeTruthy();
  const listJson = (await list.json()) as ApiOk<{
    runs: Array<{
      id: string;
      project_id: string;
      chapter_id?: string | null;
      type: string;
      provider?: string | null;
      model?: string | null;
      request_id?: string | null;
      prompt_system?: string | null;
      prompt_user?: string | null;
      params: Record<string, unknown>;
      output_text?: string | null;
      error?: unknown;
      created_at: string;
    }>;
  }>;
  const run = listJson.data.runs.find((r) => r.id === genJson.data.generation_run_id);
  expect(run).toBeTruthy();
  expect(run!.project_id).toBe(projectId);
  expect(run!.chapter_id).toBe(chapterId);
  expect(run!.params).toMatchObject({ memory_injection_enabled: true });
  expect(typeof run!.type).toBe("string");
  expect(typeof run!.created_at).toBe("string");

  const get = await request.get(`${state.backendUrl}/api/generation_runs/${genJson.data.generation_run_id}`);
  expect(get.ok()).toBeTruthy();
  const getJson = (await get.json()) as ApiOk<{ run: { id: string; project_id: string; chapter_id?: string | null } }>;
  expect(getJson.data.run.id).toBe(genJson.data.generation_run_id);
  expect(getJson.data.run.project_id).toBe(projectId);
  expect(getJson.data.run.chapter_id).toBe(chapterId);

  const bundle = await request.get(`${state.backendUrl}/api/generation_runs/${genJson.data.generation_run_id}/debug_bundle`);
  expect(bundle.ok()).toBeTruthy();
  const bundleRaw = await bundle.text();
  const bundleJson = JSON.parse(bundleRaw) as {
    schema_version: string;
    run?: { id?: string };
    prompt?: { render_log?: unknown };
    memory_retrieval_log?: unknown;
    vector_rag?: unknown;
  };
  expect(bundleJson.schema_version).toBe("debug_bundle_v1");
  expect(bundleJson.run?.id).toBe(genJson.data.generation_run_id);
  expect(bundleJson.prompt).toBeTruthy();
  expect(bundleJson.prompt).toHaveProperty("render_log");
  expect(bundleJson).toHaveProperty("vector_rag");
  expect(bundleJson).toHaveProperty("memory_retrieval_log");

  // Must not leak api keys (bootstrapProject uses "test-key").
  expect(JSON.stringify(getJson)).not.toContain("test-key");
  expect(bundleRaw).not.toContain("test-key");
  expect(bundleRaw).not.toMatch(/sk-[a-zA-Z0-9]{10,}/);
});
