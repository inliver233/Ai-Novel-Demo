import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

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

