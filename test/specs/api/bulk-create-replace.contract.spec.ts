import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("api: chapter bulk_create replace=1 overwrites existing", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const first = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters/bulk_create`, {
    data: { chapters: [{ number: 1, title: "old", plan: "" }] },
  });
  expect(first.ok()).toBeTruthy();

  const replaced = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters/bulk_create?replace=1`, {
    data: { chapters: [{ number: 1, title: "new", plan: "" }] },
  });
  expect(replaced.ok()).toBeTruthy();

  const list = await request.get(`${state.backendUrl}/api/projects/${projectId}/chapters`);
  expect(list.ok()).toBeTruthy();
  const listJson = (await list.json()) as { ok: boolean; data: { chapters: Array<{ number: number; title: string }> } };
  const c1 = listJson.data.chapters.find((c) => c.number === 1);
  expect(c1?.title).toBe("new");
});

