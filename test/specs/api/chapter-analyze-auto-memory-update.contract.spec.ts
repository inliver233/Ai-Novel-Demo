import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("api: chapter analyze supports optional auto-propose memory update (fail-soft)", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const createDone = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "用于 auto memupd", status: "done" },
  });
  expect(createDone.ok()).toBeTruthy();
  const createDoneJson = (await createDone.json()) as ApiOk<{ chapter: { id: string } }>;
  const chapterDoneId = createDoneJson.data.chapter.id;

  const updateDone = await request.put(`${state.backendUrl}/api/chapters/${chapterDoneId}`, {
    data: { title: "E2E 第一章", plan: "用于 auto memupd", content_md: "E2E 正文：用于自动记忆更新。", summary: "", status: "done" },
  });
  expect(updateDone.ok()).toBeTruthy();

  const analyzeDone = await request.post(`${state.backendUrl}/api/chapters/${chapterDoneId}/analyze`, {
    headers: { "X-LLM-Provider": "openai_compatible" },
    data: {
      instruction: "E2E analyze",
      auto_propose_memory_update: true,
      memory_update_focus: "",
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
  expect(analyzeDone.ok()).toBeTruthy();

  const analyzeDoneJson = (await analyzeDone.json()) as ApiOk<{
    generation_run_id: string;
    memory_update_auto_propose: { enabled: boolean; ok: boolean; skipped: boolean; reason?: string; change_set_id?: string };
  }>;
  expect(analyzeDoneJson.ok).toBe(true);
  expect(typeof analyzeDoneJson.request_id).toBe("string");
  expect(typeof analyzeDoneJson.data.generation_run_id).toBe("string");
  expect(analyzeDoneJson.data.memory_update_auto_propose.enabled).toBe(true);
  expect(analyzeDoneJson.data.memory_update_auto_propose.ok).toBe(true);
  expect(analyzeDoneJson.data.memory_update_auto_propose.skipped).toBe(false);
  expect(typeof analyzeDoneJson.data.memory_update_auto_propose.change_set_id).toBe("string");

  const changeSetId = analyzeDoneJson.data.memory_update_auto_propose.change_set_id!;
  const list = await request.get(`${state.backendUrl}/api/projects/${projectId}/memory_change_sets?status=proposed&limit=50`);
  expect(list.ok()).toBeTruthy();
  const listJson = (await list.json()) as ApiOk<{ items: Array<{ id: string; status: string }> }>;
  expect(listJson.data.items.some((x) => x.id === changeSetId && x.status === "proposed")).toBe(true);

  const createDraft = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 2, title: "E2E 第二章", plan: "draft chapter", status: "drafting" },
  });
  expect(createDraft.ok()).toBeTruthy();
  const createDraftJson = (await createDraft.json()) as ApiOk<{ chapter: { id: string } }>;
  const chapterDraftId = createDraftJson.data.chapter.id;

  const updateDraft = await request.put(`${state.backendUrl}/api/chapters/${chapterDraftId}`, {
    data: { title: "E2E 第二章", plan: "draft chapter", content_md: "E2E 正文：draft", summary: "", status: "drafting" },
  });
  expect(updateDraft.ok()).toBeTruthy();

  const analyzeDraft = await request.post(`${state.backendUrl}/api/chapters/${chapterDraftId}/analyze`, {
    headers: { "X-LLM-Provider": "openai_compatible" },
    data: { instruction: "E2E analyze", auto_propose_memory_update: true, context: { include_outline: false } },
  });
  expect(analyzeDraft.ok()).toBeTruthy();

  const analyzeDraftJson = (await analyzeDraft.json()) as ApiOk<{
    memory_update_auto_propose: { enabled: boolean; ok: boolean; skipped: boolean; reason?: string };
  }>;
  expect(analyzeDraftJson.data.memory_update_auto_propose.enabled).toBe(true);
  expect(analyzeDraftJson.data.memory_update_auto_propose.ok).toBe(false);
  expect(analyzeDraftJson.data.memory_update_auto_propose.skipped).toBe(true);
  expect(analyzeDraftJson.data.memory_update_auto_propose.reason).toBe("chapter_not_done");

  // Must not leak api keys or secrets (bootstrapProject uses "test-key").
  const raw = JSON.stringify({ analyzeDoneJson, analyzeDraftJson, listJson });
  expect(raw).not.toContain("test-key");
  expect(raw).not.toMatch(/sk-[a-zA-Z0-9]{10,}/);
});

