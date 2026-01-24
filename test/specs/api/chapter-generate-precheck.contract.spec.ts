import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

function stripCache(renderLog: unknown): unknown {
  if (!renderLog || typeof renderLog !== "object") return renderLog;
  const cloned = JSON.parse(JSON.stringify(renderLog)) as Record<string, unknown>;
  cloned.cache_hit = [];
  cloned.cache_miss = [];
  return cloned;
}

test("api: chapter_generate_precheck contract (macro_seed pinned)", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as ApiOk<{ chapter: { id: string } }>;
  const chapterId = createJson.data.chapter.id;

  const macroSeed = "e2e-precheck-seed";
  const body = {
    mode: "replace",
    instruction: "E2E precheck contract test",
    target_word_count: 300,
    plan_first: false,
    post_edit: false,
    post_edit_sanitize: false,
    macro_seed: macroSeed,
    memory_injection_enabled: true,
    memory_query_text: "dragon",
    memory_modules: {
      worldbook: false,
      story_memory: true,
      structured: false,
      vector_rag: false,
      graph: false,
      fractal: false,
    },
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
  };

  const precheckRes = await request.post(`${state.backendUrl}/api/chapters/${chapterId}/generate-precheck`, {
    data: body,
  });
  expect(precheckRes.ok()).toBeTruthy();
  const precheckJson = (await precheckRes.json()) as ApiOk<{
    precheck: {
      task: string;
      macro_seed: string;
      prompt_system: string;
      prompt_user: string;
      messages: Array<{ role: string; content: string; name?: string | null }>;
      render_log: unknown;
      memory_pack?: unknown;
      memory_injection_config?: unknown;
      memory_retrieval_log_json?: unknown;
      prompt_overridden: boolean;
    };
  }>;

  expect(precheckJson.ok).toBe(true);
  expect(typeof precheckJson.request_id).toBe("string");

  const precheck = precheckJson.data.precheck;
  expect(precheck.task).toBe("chapter_generate");
  expect(precheck.macro_seed).toBe(macroSeed);
  expect(typeof precheck.prompt_system).toBe("string");
  expect(typeof precheck.prompt_user).toBe("string");
  expect(precheck.prompt_system.trim().length + precheck.prompt_user.trim().length).toBeGreaterThan(0);
  expect(Array.isArray(precheck.messages)).toBe(true);
  expect(precheck.messages.length).toBeGreaterThan(0);
  for (const m of precheck.messages) {
    expect(typeof m.role).toBe("string");
    expect(typeof m.content).toBe("string");
    expect(m.name === undefined || m.name === null || typeof m.name === "string").toBe(true);
  }
  expect(precheck.render_log).toBeTruthy();
  expect(precheck.prompt_overridden).toBe(false);

  // memory_injection_enabled should surface observability fields (shape only).
  expect(precheck).toHaveProperty("memory_retrieval_log_json");
  expect(precheck).toHaveProperty("memory_injection_config");

  const genRes = await request.post(`${state.backendUrl}/api/chapters/${chapterId}/generate`, { data: body });
  expect(genRes.ok()).toBeTruthy();
  const genJson = (await genRes.json()) as ApiOk<{ generation_run_id: string }>;
  expect(typeof genJson.data.generation_run_id).toBe("string");
  expect(genJson.data.generation_run_id.length).toBeGreaterThan(0);

  const runRes = await request.get(`${state.backendUrl}/api/generation_runs/${genJson.data.generation_run_id}`);
  expect(runRes.ok()).toBeTruthy();
  const runJson = (await runRes.json()) as ApiOk<{
    run: { prompt_system?: string | null; prompt_user?: string | null; prompt_render_log?: unknown };
  }>;

  expect(runJson.data.run.prompt_system).toBe(precheck.prompt_system);
  expect(runJson.data.run.prompt_user).toBe(precheck.prompt_user);
  expect(stripCache(runJson.data.run.prompt_render_log)).toEqual(stripCache(precheck.render_log));

  // Must not leak api keys (bootstrapProject uses "test-key").
  const raw = JSON.stringify(precheckJson);
  expect(raw).not.toContain("test-key");
  expect(raw).not.toMatch(/sk-[a-zA-Z0-9]{10,}/);
});

