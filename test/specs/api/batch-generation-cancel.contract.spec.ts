import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("api: batch_generation cancel contract", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const createChapter = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "" },
  });
  expect(createChapter.ok()).toBeTruthy();

  const createTask = await request.post(`${state.backendUrl}/api/projects/${projectId}/batch_generation_tasks`, {
    data: { count: 1, include_existing: true },
  });
  expect(createTask.ok()).toBeTruthy();
  const taskJson = (await createTask.json()) as ApiOk<{ task: { id: string; status: string; cancel_requested: boolean } }>;
  const taskId = taskJson.data.task.id;
  expect(typeof taskId).toBe("string");
  expect(taskId.length).toBeGreaterThan(0);

  const cancel = await request.post(`${state.backendUrl}/api/batch_generation_tasks/${taskId}/cancel`);
  expect(cancel.ok()).toBeTruthy();
  const cancelJson = (await cancel.json()) as ApiOk<{
    task: { id: string; status: string; cancel_requested: boolean };
    canceled: boolean;
  }>;
  expect(cancelJson.data.task.id).toBe(taskId);
  expect(typeof cancelJson.data.canceled).toBe("boolean");

  const after = await request.get(`${state.backendUrl}/api/batch_generation_tasks/${taskId}`);
  expect(after.ok()).toBeTruthy();
  const afterJson = (await after.json()) as ApiOk<{ task: { id: string; status: string; cancel_requested: boolean } }>;
  expect(afterJson.data.task.id).toBe(taskId);
  expect(afterJson.data.task.status).toBe(cancelJson.data.task.status);
  expect(afterJson.data.task.cancel_requested).toBe(cancelJson.data.task.cancel_requested);

  if (cancelJson.data.canceled) {
    expect(cancelJson.data.task.cancel_requested).toBe(true);
    expect(["running", "canceled"]).toContain(cancelJson.data.task.status);
  } else {
    // In E2E, TASK_QUEUE_BACKEND=inline completes tasks synchronously, so cancel becomes a safe no-op.
    expect(["succeeded", "failed", "canceled"]).toContain(cancelJson.data.task.status);
  }

  const cancel2 = await request.post(`${state.backendUrl}/api/batch_generation_tasks/${taskId}/cancel`);
  expect(cancel2.ok()).toBeTruthy();
  const cancel2Json = (await cancel2.json()) as ApiOk<{ task: { id: string; status: string }; canceled: boolean }>;
  expect(cancel2Json.data.task.id).toBe(taskId);
  expect(cancel2Json.data.canceled).toBe(false);
  expect(cancel2Json.data.task.status).toBe(afterJson.data.task.status);
});
