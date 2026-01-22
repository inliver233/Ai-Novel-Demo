import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };
type ApiErr = { ok: false; error: { code: string; message: string; details: Record<string, unknown> }; request_id: string };

test("api: analysis/apply + annotations contract", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "要点 A；要点 B" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as ApiOk<{ chapter: { id: string } }>;
  const chapterId = createJson.data.chapter.id;

  const contentMd = "E2E 正文：用于 analysis/apply 与 annotations。关键片段：E2E_HOOK_EXCERPT。";
  const update = await request.put(`${state.backendUrl}/api/chapters/${chapterId}`, {
    data: { title: "E2E 第一章", plan: "要点 A；要点 B", content_md: contentMd, summary: "", status: "drafting" },
  });
  expect(update.ok()).toBeTruthy();

  const analysis = {
    chapter_summary: "E2E 摘要",
    hooks: [{ excerpt: "E2E_HOOK_EXCERPT", note: "钩子：用于 E2E" }],
    foreshadows: [],
    plot_points: [],
    suggestions: [],
    overall_notes: "OK",
  };

  const apply1 = await request.post(`${state.backendUrl}/api/chapters/${chapterId}/analysis/apply`, {
    data: { analysis, draft_content_md: contentMd },
  });
  expect(apply1.ok()).toBeTruthy();
  const apply1Json = (await apply1.json()) as ApiOk<{
    idempotent: boolean;
    analysis_hash: string;
    plot_analysis_id: string;
    memories: Array<{
      id: string;
      memory_type: string;
      content: string;
      importance_score: number;
      story_timeline: number;
      text_position: number;
      text_length: number;
      tags: unknown;
      metadata: unknown;
    }>;
  }>;

  expect(apply1Json.ok).toBe(true);
  expect(typeof apply1Json.request_id).toBe("string");
  expect(apply1Json.data.idempotent).toBe(false);
  expect(apply1Json.data.analysis_hash).toMatch(/^[a-f0-9]{64}$/);
  expect(typeof apply1Json.data.plot_analysis_id).toBe("string");
  expect(Array.isArray(apply1Json.data.memories)).toBe(true);
  expect(apply1Json.data.memories.length).toBeGreaterThanOrEqual(1);
  expect(apply1Json.data.memories.some((m) => m.memory_type === "hook")).toBe(true);

  const packRes = await request.get(`${state.backendUrl}/api/projects/${projectId}/memory/retrieve?query_text=E2E_HOOK_EXCERPT`);
  expect(packRes.ok()).toBeTruthy();
  const packJson = (await packRes.json()) as ApiOk<{ story_memory: Record<string, unknown> }>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const storyMemory = (packJson.data as any).story_memory as Record<string, unknown>;
  expect(storyMemory.enabled).toBe(true);
  expect(typeof storyMemory.text_md).toBe("string");
  expect(String(storyMemory.text_md)).toContain("E2E_HOOK_EXCERPT");

  const apply2 = await request.post(`${state.backendUrl}/api/chapters/${chapterId}/analysis/apply`, {
    data: { analysis, draft_content_md: contentMd },
  });
  expect(apply2.ok()).toBeTruthy();
  const apply2Json = (await apply2.json()) as ApiOk<{ idempotent: boolean; analysis_hash: string; memories: unknown[] }>;
  expect(apply2Json.ok).toBe(true);
  expect(apply2Json.data.idempotent).toBe(true);
  expect(apply2Json.data.analysis_hash).toBe(apply1Json.data.analysis_hash);
  expect(Array.isArray(apply2Json.data.memories)).toBe(true);
  expect(apply2Json.data.memories.length).toBe(apply1Json.data.memories.length);

  const annRes = await request.get(`${state.backendUrl}/api/chapters/${chapterId}/annotations`);
  expect(annRes.ok()).toBeTruthy();
  const annJson = (await annRes.json()) as ApiOk<{
    annotations: Array<{
      id: string;
      type: string;
      title: string | null;
      content: string;
      importance: number;
      position: number;
      length: number;
      tags: unknown;
      metadata: unknown;
    }>;
  }>;
  expect(annJson.ok).toBe(true);
  expect(typeof annJson.request_id).toBe("string");
  expect(Array.isArray(annJson.data.annotations)).toBe(true);
  expect(annJson.data.annotations.some((a) => a.type === "hook")).toBe(true);

  // Must not leak api keys or secrets (bootstrapProject uses "test-key").
  const raw = JSON.stringify({ apply1Json, apply2Json, annJson });
  expect(raw).not.toContain("test-key");
  expect(raw).not.toMatch(/sk-[a-zA-Z0-9]{10,}/);
});

test("api: analysis/apply rejects unknown analysis fields (fail-closed)", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "要点 A；要点 B" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as ApiOk<{ chapter: { id: string } }>;
  const chapterId = createJson.data.chapter.id;

  const contentMd = "E2E 正文：用于 analysis/apply fail-closed。";
  const update = await request.put(`${state.backendUrl}/api/chapters/${chapterId}`, {
    data: { title: "E2E 第一章", plan: "要点 A；要点 B", content_md: contentMd, summary: "", status: "drafting" },
  });
  expect(update.ok()).toBeTruthy();

  const analysis = {
    chapter_summary: "E2E 摘要",
    hooks: [{ excerpt: "E2E_HOOK_EXCERPT", note: "钩子：用于 E2E" }],
    foreshadows: [],
    plot_points: [],
    suggestions: [],
    overall_notes: "OK",
    unknown_field: "MUST_FAIL",
  };

  const apply = await request.post(`${state.backendUrl}/api/chapters/${chapterId}/analysis/apply`, {
    data: { analysis, draft_content_md: contentMd },
  });
  expect(apply.ok()).toBeFalsy();
  expect(apply.status()).toBe(400);
  const applyJson = (await apply.json()) as ApiErr;
  expect(applyJson.ok).toBe(false);
  expect(typeof applyJson.request_id).toBe("string");
  expect(applyJson.error.code).toBe("ANALYSIS_SCHEMA_ERROR");
  expect(Array.isArray(applyJson.error.details.unknown_fields)).toBe(true);
});

test("api: chapter rewrite returns content_md + raw_output", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "要点 A；要点 B" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as ApiOk<{ chapter: { id: string } }>;
  const chapterId = createJson.data.chapter.id;

  const contentMd = "E2E 原始正文：用于章节重写 contract。";
  const update = await request.put(`${state.backendUrl}/api/chapters/${chapterId}`, {
    data: { title: "E2E 第一章", plan: "要点 A；要点 B", content_md: contentMd, summary: "", status: "drafting" },
  });
  expect(update.ok()).toBeTruthy();

  const rewrite = await request.post(`${state.backendUrl}/api/chapters/${chapterId}/rewrite`, {
    headers: { "X-LLM-Provider": "openai_compatible" },
    data: {
      instruction: "E2E rewrite contract test",
      analysis: { overall_notes: "rewrite with improvements" },
      draft_content_md: contentMd,
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
  expect(rewrite.ok()).toBeTruthy();

  const rewriteJson = (await rewrite.json()) as ApiOk<{
    content_md: string;
    raw_output: string;
    generation_run_id: string;
  }>;
  expect(rewriteJson.ok).toBe(true);
  expect(typeof rewriteJson.request_id).toBe("string");
  expect(typeof rewriteJson.data.content_md).toBe("string");
  expect(rewriteJson.data.content_md.length).toBeGreaterThan(0);
  expect(typeof rewriteJson.data.raw_output).toBe("string");
  expect(typeof rewriteJson.data.generation_run_id).toBe("string");
  expect(rewriteJson.data.generation_run_id.length).toBeGreaterThan(0);

  // Must not leak api keys or secrets (bootstrapProject uses "test-key").
  const raw = JSON.stringify(rewriteJson);
  expect(raw).not.toContain("test-key");
  expect(raw).not.toMatch(/sk-[a-zA-Z0-9]{10,}/);
});
