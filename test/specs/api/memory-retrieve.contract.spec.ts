import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("api: memory/retrieve returns stable empty pack structure", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const res = await request.get(`${state.backendUrl}/api/projects/${projectId}/memory/retrieve`);
  expect(res.ok()).toBeTruthy();

  const json = (await res.json()) as ApiOk<{
    worldbook: Record<string, unknown>;
    story_memory: Record<string, unknown>;
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
  expect(typeof json.data.structured).toBe("object");
  expect(typeof json.data.vector_rag).toBe("object");
  expect(typeof json.data.graph).toBe("object");
  expect(typeof json.data.fractal).toBe("object");
  expect(Array.isArray(json.data.logs)).toBe(true);
});

