import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("api: memory/retrieve returns stable pack structure", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const res = await request.get(`${state.backendUrl}/api/projects/${projectId}/memory/retrieve`);
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

  // Must not stay in Phase0 placeholders for implemented modules.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  expect((json.data as any).story_memory.disabled_reason).not.toBe("not_implemented");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  expect((json.data as any).structured.disabled_reason).not.toBe("not_implemented");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  expect((json.data as any).graph.disabled_reason).not.toBe("not_implemented");

  const logs = json.data.logs as Array<Record<string, unknown>>;
  const sections = new Set(logs.map((l) => (typeof l.section === "string" ? l.section : "")));
  for (const key of ["worldbook", "story_memory", "semantic_history", "foreshadow_open_loops", "structured", "vector_rag", "graph", "fractal"] as const) {
    expect(sections.has(key)).toBe(true);
  }

  // Must not leak api keys (bootstrapProject uses "test-key").
  const raw = JSON.stringify(json);
  expect(raw).not.toContain("test-key");
  expect(raw).not.toMatch(/sk-[a-zA-Z0-9]{10,}/);
});
