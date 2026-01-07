import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("api: batch_generation enforces sequential gaps (missing chapter numbers)", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  // Create chapters 1..11 and 13 (intentionally omit 12).
  const chapters = [];
  for (let n = 1; n <= 11; n += 1) chapters.push({ number: n, title: `第 ${n} 章`, plan: "" });
  chapters.push({ number: 13, title: "第 13 章", plan: "" });

  const bulk = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters/bulk_create`, {
    data: { chapters },
  });
  expect(bulk.ok()).toBeTruthy();
  const bulkJson = (await bulk.json()) as ApiOk<{ chapters: Array<{ id: string; number: number }> }>;
  const byNumber = new Map<number, string>();
  for (const c of bulkJson.data.chapters) byNumber.set(c.number, c.id);
  const chapter10Id = byNumber.get(10);
  expect(typeof chapter10Id).toBe("string");

  // Make prerequisites 1..10 non-empty.
  for (let n = 1; n <= 10; n += 1) {
    const id = byNumber.get(n);
    expect(typeof id).toBe("string");
    const res = await request.put(`${state.backendUrl}/api/chapters/${id}`, {
      data: { content_md: `E2E seed content (chapter ${n})` },
    });
    expect(res.ok()).toBeTruthy();
  }

  // Request generating 2 chapters after chapter 10: it would pick 11 and 13, but must reject missing chapter 12.
  const createTask = await request.post(`${state.backendUrl}/api/projects/${projectId}/batch_generation_tasks`, {
    data: {
      after_chapter_id: chapter10Id,
      count: 2,
      include_existing: false,
      instruction: "E2E batch sequential gap test",
      context: {
        include_world_setting: false,
        include_style_guide: false,
        include_constraints: false,
        include_outline: false,
        include_smart_context: false,
        require_sequential: true,
        character_ids: [],
        previous_chapter: "none",
      },
    },
  });
  expect(createTask.status()).toBe(400);

  const json = (await createTask.json()) as {
    ok: boolean;
    error?: { code?: string; details?: { missing_numbers?: number[] } };
  };
  expect(json.ok).toBe(false);
  expect(json.error?.code).toBe("CHAPTER_PREREQ_MISSING");
  expect(json.error?.details?.missing_numbers).toContain(12);
});

