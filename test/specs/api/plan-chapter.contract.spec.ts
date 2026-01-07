import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("api: chapter_plan contract", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "要点 A；要点 B" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as ApiOk<{ chapter: { id: string } }>;
  const chapterId = createJson.data.chapter.id;

  const plan = await request.post(`${state.backendUrl}/api/chapters/${chapterId}/plan`, {
    headers: { "X-LLM-Provider": "openai_compatible" },
    data: {
      instruction: "E2E plan contract test",
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
  expect(plan.ok()).toBeTruthy();

  const planJson = (await plan.json()) as ApiOk<{ plan: string; raw_output: string }>;
  expect(planJson.ok).toBe(true);
  expect(typeof planJson.request_id).toBe("string");
  expect(typeof planJson.data.plan).toBe("string");
  expect(planJson.data.plan).toContain("规划");
  expect(planJson.data.raw_output).toContain("<plan>");

  // Must not leak api keys (bootstrapProject uses "test-key").
  expect(JSON.stringify(planJson)).not.toContain("test-key");
});

