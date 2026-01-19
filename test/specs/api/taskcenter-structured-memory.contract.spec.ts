import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("api: taskcenter + structured_memory contract (filters + paging)", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "用于 contract", status: "done" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as ApiOk<{ chapter: { id: string } }>;
  const chapterId = createJson.data.chapter.id;

  const proposeAndApply = async (suffix: string) => {
    const propose = await request.post(`${state.backendUrl}/api/chapters/${chapterId}/memory/propose`, {
      data: {
        schema_version: "memory_update_v1",
        idempotency_key: `e2e-contract-${Date.now()}-${suffix}`,
        title: `E2E Contract ${suffix}`,
        ops: [
          {
            op: "upsert",
            target_table: "entities",
            after: { entity_type: "character", name: `Alice-${suffix}`, summary_md: "E2E" },
            evidence_ids: [],
          },
        ],
      },
    });
    expect(propose.ok()).toBeTruthy();
    const proposeJson = (await propose.json()) as ApiOk<{ change_set: { id: string } }>;
    const changeSetId = proposeJson.data.change_set.id;

    const apply = await request.post(`${state.backendUrl}/api/memory_change_sets/${changeSetId}/apply`);
    expect(apply.ok()).toBeTruthy();
    return changeSetId;
  };

  await proposeAndApply("A");
  await new Promise((r) => setTimeout(r, 1100));
  await proposeAndApply("B");

  // ChangeSets: list + status filter + paging.
  const listCs1 = await request.get(`${state.backendUrl}/api/projects/${projectId}/memory_change_sets?limit=1`);
  expect(listCs1.ok()).toBeTruthy();
  const cs1 = (await listCs1.json()) as ApiOk<{ items: Array<Record<string, unknown>>; next_before: string | null }>;
  expect(cs1.data.items.length).toBe(1);

  const firstCs = cs1.data.items[0]!;
  expect(typeof firstCs.id).toBe("string");
  expect(typeof firstCs.status).toBe("string");
  expect(Object.prototype.hasOwnProperty.call(firstCs, "request_id")).toBe(true);
  expect(Object.prototype.hasOwnProperty.call(firstCs, "idempotency_key")).toBe(true);
  expect(Object.prototype.hasOwnProperty.call(firstCs, "title")).toBe(true);
  expect(typeof cs1.data.next_before).toBe("string");

  const listCs2 = await request.get(
    `${state.backendUrl}/api/projects/${projectId}/memory_change_sets?limit=1&before=${encodeURIComponent(cs1.data.next_before!)}`,
  );
  expect(listCs2.ok()).toBeTruthy();
  const cs2 = (await listCs2.json()) as ApiOk<{ items: Array<Record<string, unknown>> }>;
  expect(cs2.data.items.length).toBe(1);
  expect(String(cs2.data.items[0]!.id)).not.toBe(String(firstCs.id));

  const listApplied = await request.get(`${state.backendUrl}/api/projects/${projectId}/memory_change_sets?status=applied&limit=50`);
  expect(listApplied.ok()).toBeTruthy();
  const applied = (await listApplied.json()) as ApiOk<{ items: Array<{ status: string }> }>;
  expect(applied.data.items.length).toBeGreaterThan(0);
  expect(applied.data.items.every((x) => x.status === "applied")).toBe(true);

  // Tasks: list + paging. (status filter is covered by UI test; here focus on contract + paging)
  const listTasks1 = await request.get(`${state.backendUrl}/api/projects/${projectId}/memory_tasks?limit=1`);
  expect(listTasks1.ok()).toBeTruthy();
  const tasks1 = (await listTasks1.json()) as ApiOk<{ items: Array<Record<string, unknown>>; next_before: string | null }>;
  expect(tasks1.data.items.length).toBe(1);

  const firstTask = tasks1.data.items[0]!;
  expect(typeof firstTask.id).toBe("string");
  expect(typeof firstTask.kind).toBe("string");
  expect(Object.prototype.hasOwnProperty.call(firstTask, "request_id")).toBe(true);
  expect(["queued", "running", "done", "failed"]).toContain(String(firstTask.status));
  expect(typeof tasks1.data.next_before).toBe("string");

  const listTasks2 = await request.get(
    `${state.backendUrl}/api/projects/${projectId}/memory_tasks?limit=1&before=${encodeURIComponent(tasks1.data.next_before!)}`,
  );
  expect(listTasks2.ok()).toBeTruthy();
  const tasks2 = (await listTasks2.json()) as ApiOk<{ items: Array<Record<string, unknown>> }>;
  expect(tasks2.data.items.length).toBe(1);
  expect(String(tasks2.data.items[0]!.id)).not.toBe(String(firstTask.id));

  // Structured memory: q filter + paging (cursor/before).
  const sm1 = await request.get(`${state.backendUrl}/api/projects/${projectId}/memory/structured?table=entities&limit=1`);
  expect(sm1.ok()).toBeTruthy();
  const sm1Json = (await sm1.json()) as ApiOk<{
    counts: Record<string, number>;
    cursor: Record<string, string | null>;
    entities: Array<{ id: string; name: string }>;
  }>;
  expect(sm1Json.data.entities.length).toBe(1);
  expect(typeof sm1Json.data.cursor.entities).toBe("string");

  const before = sm1Json.data.cursor.entities!;
  const firstEntityId = sm1Json.data.entities[0]!.id;
  const sm2 = await request.get(`${state.backendUrl}/api/projects/${projectId}/memory/structured?table=entities&limit=1&before=${encodeURIComponent(before)}`);
  expect(sm2.ok()).toBeTruthy();
  const sm2Json = (await sm2.json()) as ApiOk<{ entities: Array<{ id: string }> }>;
  expect(sm2Json.data.entities.length).toBe(1);
  expect(sm2Json.data.entities[0]!.id).not.toBe(firstEntityId);

  const smQ = await request.get(`${state.backendUrl}/api/projects/${projectId}/memory/structured?table=entities&q=Alice-A&limit=50`);
  expect(smQ.ok()).toBeTruthy();
  const smQJson = (await smQ.json()) as ApiOk<{ entities: Array<{ name: string }> }>;
  expect(smQJson.data.entities.some((e) => e.name === "Alice-A")).toBe(true);
});
