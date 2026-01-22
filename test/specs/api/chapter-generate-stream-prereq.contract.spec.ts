import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("api: chapter generate-stream require_sequential rejects missing prereq chapters", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const c1 = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "第 1 章", plan: "占位" },
  });
  expect(c1.ok()).toBeTruthy();

  const c2 = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 2, title: "第 2 章", plan: "应触发前置检查" },
  });
  expect(c2.ok()).toBeTruthy();
  const c2Json = (await c2.json()) as ApiOk<{ chapter: { id: string } }>;
  const chapter2Id = c2Json.data.chapter.id;

  const res = await request.post(`${state.backendUrl}/api/chapters/${chapter2Id}/generate-stream`, {
    headers: { "X-LLM-Provider": "openai_compatible" },
    data: {
      mode: "replace",
      instruction: "E2E prereq missing stream contract test",
      target_word_count: 300,
      plan_first: false,
      post_edit: false,
      memory_injection_enabled: false,
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
  expect(res.status()).toBe(400);

  const json = (await res.json()) as {
    ok: boolean;
    error?: { code?: string; details?: { missing_numbers?: number[] } };
  };
  expect(json.ok).toBe(false);
  expect(json.error?.code).toBe("CHAPTER_PREREQ_MISSING");
  expect(json.error?.details?.missing_numbers).toContain(1);

  // Must not leak api keys (bootstrapProject uses "test-key").
  expect(JSON.stringify(json)).not.toContain("test-key");
});

