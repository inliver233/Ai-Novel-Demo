import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("api: memory/preview accepts modules + budget_overrides and returns stable pack structure", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const res = await request.post(`${state.backendUrl}/api/projects/${projectId}/memory/preview`, {
    data: {
      query_text: "dragon",
      section_enabled: {
        worldbook: false,
        story_memory: true,
        semantic_history: false,
        foreshadow_open_loops: false,
        structured: false,
        vector_rag: false,
        graph: false,
        fractal: false,
      },
      budget_overrides: {
        worldbook: 123,
        story_memory: 456,
      },
    },
  });
  expect(res.ok()).toBeTruthy();

  const json = (await res.json()) as ApiOk<{
    worldbook: Record<string, unknown>;
    story_memory: Record<string, unknown>;
    semantic_history: Record<string, unknown>;
    foreshadow_open_loops: Record<string, unknown>;
    structured: Record<string, unknown>;
    vector_rag: Record<string, unknown>;
    graph: Record<string, unknown>;
    fractal: Record<string, unknown>;
    logs: unknown[];
  }>;
  expect(json.ok).toBe(true);
  expect(typeof json.request_id).toBe("string");

  expect(json.data).toBeTruthy();
  expect(typeof json.data.worldbook).toBe("object");
  expect(typeof json.data.story_memory).toBe("object");
  expect(typeof json.data.semantic_history).toBe("object");
  expect(typeof json.data.foreshadow_open_loops).toBe("object");
  expect(typeof json.data.structured).toBe("object");
  expect(typeof json.data.vector_rag).toBe("object");
  expect(typeof json.data.graph).toBe("object");
  expect(typeof json.data.fractal).toBe("object");
  expect(Array.isArray(json.data.logs)).toBe(true);

  for (const key of ["worldbook", "story_memory", "semantic_history", "foreshadow_open_loops", "structured", "vector_rag", "graph", "fractal"] as const) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const section = (json.data as any)[key] as Record<string, unknown>;
    expect(typeof section.enabled).toBe("boolean");
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(section.disabled_reason === null || typeof (section as any).disabled_reason === "string").toBeTruthy();
  }

  // section_enabled should be applied.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  expect((json.data as any).worldbook.enabled).toBe(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  expect((json.data as any).worldbook.disabled_reason).toBe("disabled");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  expect((json.data as any).semantic_history.enabled).toBe(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  expect((json.data as any).semantic_history.disabled_reason).toBe("disabled");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  expect((json.data as any).foreshadow_open_loops.enabled).toBe(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  expect((json.data as any).foreshadow_open_loops.disabled_reason).toBe("disabled");

  // story_memory should echo query_text when section is enabled (even if empty).
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  expect((json.data as any).story_memory.query_text).toBe("dragon");

  const logs = json.data.logs as Array<Record<string, unknown>>;
  const sections = new Set(logs.map((l) => (typeof l.section === "string" ? l.section : "")));
  for (const key of ["worldbook", "story_memory", "semantic_history", "foreshadow_open_loops", "structured", "vector_rag", "graph", "fractal"] as const) {
    expect(sections.has(key)).toBe(true);
  }

  const wbLog = logs.find((l) => l.section === "worldbook");
  expect(wbLog).toBeTruthy();
  expect(wbLog?.budget_source).toBe("override");
  expect(wbLog?.budget_char_limit).toBe(123);

  const smLog = logs.find((l) => l.section === "story_memory");
  expect(smLog).toBeTruthy();
  expect(smLog?.budget_source).toBe("override");
  expect(smLog?.budget_char_limit).toBe(456);

  // Must not leak api keys (bootstrapProject uses "test-key").
  const raw = JSON.stringify(json);
  expect(raw).not.toContain("test-key");
  expect(raw).not.toMatch(/sk-[a-zA-Z0-9]{10,}/);
});
