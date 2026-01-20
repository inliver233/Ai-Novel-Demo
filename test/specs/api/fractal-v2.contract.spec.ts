import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

type PromptBlock = { identifier: string; role: string; text_md: string };

test("api: fractal v2 rebuild falls back when llm_preset missing", async ({ request }) => {
  const state = loadState();

  const projectRes = await request.post(`${state.backendUrl}/api/projects`, {
    data: { name: "E2E Fractal v2 (no preset)", genre: "Test", logline: "fractal_v2 preset missing fallback" },
  });
  expect(projectRes.ok()).toBeTruthy();
  const projectJson = (await projectRes.json()) as ApiOk<{ project: { id: string } }>;
  const projectId = projectJson.data.project.id;

  const chapterRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: {
      number: 1,
      title: "E2E 第一章",
      plan: "Alice 与 Bob 发生冲突，留下伏笔。",
      status: "done",
    },
  });
  expect(chapterRes.ok()).toBeTruthy();

  const rebuildRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/fractal/rebuild`, {
    data: { reason: "e2e_v2_preset_missing", mode: "llm_v2" },
  });
  expect(rebuildRes.ok()).toBeTruthy();

  const json = (await rebuildRes.json()) as ApiOk<{
    result: {
      enabled: boolean;
      disabled_reason: string | null;
      config: Record<string, unknown>;
      v2: Record<string, unknown>;
      prompt_block: PromptBlock;
      prompt_block_v2: PromptBlock;
      updated_at: string;
    };
  }>;
  expect(json.ok).toBe(true);
  expect(typeof json.request_id).toBe("string");

  const out = json.data.result;
  expect(out.enabled).toBe(true);
  expect(out.disabled_reason).toBeNull();

  // Fallback must be explicit.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  expect(Boolean((out.v2 as any).enabled)).toBe(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  expect((out.v2 as any).disabled_reason).toBe("llm_preset_missing");

  expect(out.prompt_block.identifier).toBe("sys.memory.fractal");
  expect(out.prompt_block.role).toBe("system");
  expect(out.prompt_block.text_md).toContain("<FractalMemory>");
  expect(out.prompt_block.text_md).toContain("</FractalMemory>");

  // v2 is empty when fallback.
  expect(out.prompt_block_v2.identifier).toBe("sys.memory.fractal_v2");
  expect(out.prompt_block_v2.role).toBe("system");
  expect(out.prompt_block_v2.text_md).toBe("");
});

test("api: fractal v2 rebuild records parse_error fallback when mock output violates tag contract", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const chapterRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: {
      number: 1,
      title: "E2E 第一章",
      plan: "Alice 与 Bob 发生冲突，留下伏笔。",
      status: "done",
    },
  });
  expect(chapterRes.ok()).toBeTruthy();

  const rebuildRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/fractal/rebuild`, {
    data: { reason: "e2e_v2_parse_error", mode: "llm_v2" },
  });
  expect(rebuildRes.ok()).toBeTruthy();

  const json = (await rebuildRes.json()) as ApiOk<{
    result: {
      enabled: boolean;
      disabled_reason: string | null;
      config: Record<string, unknown>;
      v2: Record<string, unknown>;
      prompt_block: PromptBlock;
      prompt_block_v2: PromptBlock;
      updated_at: string;
    };
  }>;
  expect(json.ok).toBe(true);

  const out = json.data.result;
  expect(out.enabled).toBe(true);

  // Our test mock does not emit <fractal_v2>...</fractal_v2>, so v2 should fallback with parse_error.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const v2 = out.v2 as any;
  expect(Boolean(v2.enabled)).toBe(false);
  expect(v2.disabled_reason).toBe("parse_error");
  expect(typeof v2.run_id).toBe("string");
  expect(v2.finish_reason === null || typeof v2.finish_reason === "string").toBeTruthy();
  expect(Array.isArray(v2.warnings)).toBe(true);
  expect(typeof v2.parse_error).toBe("object");

  // Deterministic output must still be present.
  expect(out.prompt_block.text_md).toContain("<FractalMemory>");
});

