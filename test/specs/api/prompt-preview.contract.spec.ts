import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("api: prompt_preview contract", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const presets = await request.get(`${state.backendUrl}/api/projects/${projectId}/prompt_presets`);
  expect(presets.ok()).toBeTruthy();
  const presetsJson = (await presets.json()) as ApiOk<{ presets: Array<{ id: string; name: string }> }>;
  const presetId =
    presetsJson.data.presets.find((p) => p.name.includes("章节生成"))?.id ?? presetsJson.data.presets[0]?.id;
  expect(typeof presetId).toBe("string");
  expect((presetId ?? "").length).toBeGreaterThan(0);

  const values = {
    project_name: "E2E Project",
    genre: "Test",
    logline: "E2E automated test project",
    world_setting: "E2E world_setting",
    style_guide: "E2E style_guide",
    constraints: "E2E constraints",
    characters: "- Alice（Protagonist）",
    outline: "# E2E outline",
    chapter_number: "1",
    chapter_title: "第一章",
    chapter_plan: "（示例要点）",
    chapter_summary: "（示例摘要）",
    chapter_content_md: "（示例章节正文）",
    analysis_json: JSON.stringify({ chapter_summary: "（示例分析摘要）" }),
    requirements: JSON.stringify({ chapter_count: 12 }),
    instruction: "（示例指令）",
    previous_chapter: "（示例上一章摘要）",
    target_word_count: "2500",
    raw_content: "（示例已生成正文）",
    story_plan: "（示例规划）",
    smart_context_recent_summaries: "（示例 smart_context_recent_summaries）",
    smart_context_recent_full: "（示例 smart_context_recent_full）",
    smart_context_story_skeleton: "（示例 smart_context_story_skeleton）",
    project: {
      name: "E2E Project",
      genre: "Test",
      logline: "E2E automated test project",
      world_setting: "E2E world_setting",
      style_guide: "E2E style_guide",
      constraints: "E2E constraints",
      characters: "- Alice（Protagonist）",
    },
    story: {
      outline: "# E2E outline",
      chapter_number: 1,
      chapter_title: "第一章",
      chapter_plan: "（示例要点）",
      chapter_summary: "（示例摘要）",
      previous_chapter: "（示例上一章摘要）",
      plan: "（示例规划）",
      raw_content: "（示例已生成正文）",
      chapter_content_md: "（示例章节正文）",
      analysis_json: JSON.stringify({ chapter_summary: "（示例分析摘要）" }),
      smart_context_recent_summaries: "（示例 smart_context_recent_summaries）",
      smart_context_recent_full: "（示例 smart_context_recent_full）",
      smart_context_story_skeleton: "（示例 smart_context_story_skeleton）",
    },
    user: { instruction: "（示例指令）", requirements: { chapter_count: 12 } },
  };

  const res = await request.post(`${state.backendUrl}/api/projects/${projectId}/prompt_preview`, {
    data: { task: "chapter_generate", preset_id: presetId, values },
  });
  expect(res.ok()).toBeTruthy();

  const json = (await res.json()) as ApiOk<{
    preview: {
      preset_id: string;
      task: string;
      system: string;
      user: string;
      prompt_tokens_estimate: number;
      prompt_budget_tokens: number | null;
      missing: string[];
      blocks: Array<{
        id: string;
        identifier: string;
        role: string;
        enabled: boolean;
        text: string;
        missing: string[];
        token_estimate: number;
      }>;
    };
    render_log?: unknown;
  }>;

  expect(json.ok).toBe(true);
  expect(typeof json.request_id).toBe("string");
  expect(json.request_id.length).toBeGreaterThan(0);

  const preview = json.data.preview;
  expect(preview.task).toBe("chapter_generate");
  expect(preview.preset_id).toBe(presetId);

  expect(typeof preview.system).toBe("string");
  expect(typeof preview.user).toBe("string");
  expect(preview.system.trim().length + preview.user.trim().length).toBeGreaterThan(0);

  expect(Number.isInteger(preview.prompt_tokens_estimate)).toBe(true);
  expect(preview.prompt_tokens_estimate).toBeGreaterThanOrEqual(0);

  expect(preview.prompt_budget_tokens === null || Number.isInteger(preview.prompt_budget_tokens)).toBe(true);
  expect(Array.isArray(preview.missing)).toBe(true);
  for (const m of preview.missing) expect(typeof m).toBe("string");

  expect(Array.isArray(preview.blocks)).toBe(true);
  expect(preview.blocks.length).toBeGreaterThan(0);
  for (const b of preview.blocks) {
    expect(typeof b.id).toBe("string");
    expect(b.id.length).toBeGreaterThan(0);
    expect(typeof b.identifier).toBe("string");
    expect(b.identifier.length).toBeGreaterThan(0);
    expect(typeof b.role).toBe("string");
    expect(typeof b.enabled).toBe("boolean");
    expect(typeof b.text).toBe("string");
    expect(Array.isArray(b.missing)).toBe(true);
    for (const m of b.missing) expect(typeof m).toBe("string");
    expect(Number.isInteger(b.token_estimate)).toBe(true);
    expect(b.token_estimate).toBeGreaterThanOrEqual(0);
  }
  expect(new Set(preview.blocks.map((b) => b.id)).size).toBe(preview.blocks.length);
  expect(new Set(preview.blocks.map((b) => b.identifier)).size).toBe(preview.blocks.length);

  // render_log observability: context optimizer + unified budget summary must exist and stay shape-stable.
  expect(json.data.render_log).toBeTruthy();
  const renderLog = json.data.render_log as {
    context_optimizer?: unknown;
    unified_context_budget?: unknown;
    cache_hit?: unknown;
    cache_miss?: unknown;
  };
  expect(renderLog).toHaveProperty("context_optimizer");
  expect(renderLog).toHaveProperty("unified_context_budget");
  expect(Array.isArray(renderLog.cache_hit)).toBe(true);
  expect(Array.isArray(renderLog.cache_miss)).toBe(true);

  const ctxOpt = (renderLog as { context_optimizer: unknown }).context_optimizer as unknown;
  expect(Boolean(ctxOpt) && typeof ctxOpt === "object").toBe(true);
  expect(typeof (ctxOpt as { enabled?: unknown }).enabled).toBe("boolean");

  const unified = (renderLog as { unified_context_budget: unknown }).unified_context_budget as unknown;
  expect(Boolean(unified) && typeof unified === "object").toBe(true);

  const unifiedObj = unified as {
    enabled?: unknown;
    before?: unknown;
    after?: unknown;
    budget_tokens?: unknown;
    dropped_blocks?: unknown;
    trimmed_blocks?: unknown;
  };
  expect(typeof unifiedObj.enabled).toBe("boolean");
  expect(unifiedObj.budget_tokens === null || typeof unifiedObj.budget_tokens === "number").toBe(true);
  expect(Number.isInteger(unifiedObj.dropped_blocks)).toBe(true);
  expect(Number.isInteger(unifiedObj.trimmed_blocks)).toBe(true);

  expect(Boolean(unifiedObj.before) && typeof unifiedObj.before === "object").toBe(true);
  expect(Boolean(unifiedObj.after) && typeof unifiedObj.after === "object").toBe(true);

  const before = unifiedObj.before as { smart_context?: unknown; memory_pack?: unknown; total?: unknown };
  const after = unifiedObj.after as { smart_context?: unknown; memory_pack?: unknown; total?: unknown };
  expect(Number.isInteger(before.smart_context)).toBe(true);
  expect(Number.isInteger(before.memory_pack)).toBe(true);
  expect(Number.isInteger(before.total)).toBe(true);
  expect(Number.isInteger(after.smart_context)).toBe(true);
  expect(Number.isInteger(after.memory_pack)).toBe(true);
  expect(Number.isInteger(after.total)).toBe(true);

  // Must not leak api keys or secrets (bootstrapProject uses "test-key").
  const raw = JSON.stringify(json);
  expect(raw).not.toContain("test-key");
  expect(raw).not.toMatch(/sk-[a-zA-Z0-9]{10,}/);
});

test("api: prompt_preview supports content_optimize task", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const presets = await request.get(`${state.backendUrl}/api/projects/${projectId}/prompt_presets`);
  expect(presets.ok()).toBeTruthy();
  const presetsJson = (await presets.json()) as ApiOk<{
    presets: Array<{ id: string; name: string; active_for?: string[] }>;
  }>;
  const preset =
    presetsJson.data.presets.find((p) => Array.isArray(p.active_for) && p.active_for.includes("content_optimize")) ??
    presetsJson.data.presets.find((p) => p.name.includes("content_optimize")) ??
    null;
  expect(Boolean(preset?.id)).toBeTruthy();

  const res = await request.post(`${state.backendUrl}/api/projects/${projectId}/prompt_preview`, {
    data: {
      task: "content_optimize",
      preset_id: preset?.id,
      values: {
        raw_content: "这是原始正文。需要保持剧情事实，仅优化表达和可读性。",
        story: {
          raw_content: "这是原始正文。需要保持剧情事实，仅优化表达和可读性。",
        },
      },
    },
  });
  expect(res.ok()).toBeTruthy();
  const json = (await res.json()) as ApiOk<{
    preview: { task: string; preset_id: string; system: string; user: string };
  }>;
  expect(json.ok).toBe(true);
  expect(json.data.preview.task).toBe("content_optimize");
  expect(typeof json.data.preview.preset_id).toBe("string");
  expect(json.data.preview.system.length + json.data.preview.user.length).toBeGreaterThan(0);
});

test("api: prompt_preview invalid task returns validation error", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const res = await request.post(`${state.backendUrl}/api/projects/${projectId}/prompt_preview`, {
    data: { task: "not_a_task", values: {} },
  });
  expect(res.status()).toBe(400);
  const json = (await res.json()) as { ok: boolean; error?: { code?: string } };
  expect(json.ok).toBe(false);
  expect(json.error?.code).toBe("VALIDATION_ERROR");
});
