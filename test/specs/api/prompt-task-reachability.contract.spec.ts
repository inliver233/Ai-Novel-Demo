import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

const PROMPT_TASKS = [
  "outline_generate",
  "chapter_generate",
  "plan_chapter",
  "post_edit",
  "content_optimize",
  "chapter_analyze",
  "chapter_rewrite",
] as const;

const PREVIEW_VALUES = {
  project_name: "E2E Reachability Project",
  genre: "Test",
  logline: "Prompt task reachability",
  world_setting: "world",
  style_guide: "style",
  constraints: "constraints",
  characters: "- Alice",
  outline: "# Outline",
  chapter_number: "1",
  chapter_title: "第一章",
  chapter_plan: "要点 A",
  chapter_summary: "摘要",
  chapter_content_md: "正文",
  analysis_json: JSON.stringify({ chapter_summary: "分析摘要" }),
  requirements: JSON.stringify({ chapter_count: 1 }),
  instruction: "请生成",
  previous_chapter: "上一章摘要",
  target_word_count: "1500",
  raw_content: "原始正文",
  story_plan: "规划",
  project: {
    name: "E2E Reachability Project",
    genre: "Test",
    logline: "Prompt task reachability",
    world_setting: "world",
    style_guide: "style",
    constraints: "constraints",
    characters: "- Alice",
  },
  story: {
    outline: "# Outline",
    chapter_number: 1,
    chapter_title: "第一章",
    chapter_plan: "要点 A",
    chapter_summary: "摘要",
    chapter_content_md: "正文",
    analysis_json: JSON.stringify({ chapter_summary: "分析摘要" }),
    previous_chapter: "上一章摘要",
    plan: "规划",
    raw_content: "原始正文",
  },
  user: { instruction: "请生成", requirements: { chapter_count: 1 } },
};

test("api: prompt task reachability registry", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const presetsRes = await request.get(`${state.backendUrl}/api/projects/${projectId}/prompt_presets`);
  expect(presetsRes.ok()).toBeTruthy();

  const resourcesRes = await request.get(`${state.backendUrl}/api/projects/${projectId}/prompt_preset_resources`);
  expect(resourcesRes.ok()).toBeTruthy();
  const resourcesJson = (await resourcesRes.json()) as ApiOk<{
    resources: Array<{ key: string; activation_tasks: string[]; preset_id?: string | null }>;
  }>;

  const presetByTask = new Map<string, string>();
  for (const resource of resourcesJson.data.resources ?? []) {
    const presetId = typeof resource.preset_id === "string" ? resource.preset_id : "";
    if (!presetId) continue;
    for (const task of resource.activation_tasks ?? []) {
      if (!presetByTask.has(task)) presetByTask.set(task, presetId);
    }
  }

  for (const task of PROMPT_TASKS) {
    const presetId = presetByTask.get(task) ?? "";
    expect(presetId.length).toBeGreaterThan(0);

    const previewRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/prompt_preview`, {
      data: {
        task,
        preset_id: presetId,
        values: PREVIEW_VALUES,
      },
    });
    expect(previewRes.ok()).toBeTruthy();
    const previewJson = (await previewRes.json()) as ApiOk<{ preview: { task: string } }>;
    expect(previewJson.data.preview.task).toBe(task);
  }
});
