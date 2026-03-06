import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("api: chapter meta contract stays lightweight while legacy/detail keep full payload", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const bulk = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters/bulk_create`, {
    data: {
      chapters: [
        { number: 1, title: "Meta 1", plan: "Plan 1" },
        { number: 2, title: "Meta 2", plan: "" },
      ],
    },
  });
  expect(bulk.ok()).toBeTruthy();
  const bulkJson = (await bulk.json()) as ApiOk<{ chapters: Array<{ id: string; number: number }> }>;
  const chapter1 = bulkJson.data.chapters.find((chapter) => chapter.number === 1);
  expect(chapter1).toBeTruthy();

  const seed = await request.put(`${state.backendUrl}/api/chapters/${chapter1!.id}`, {
    data: { content_md: "# C1", summary: "Summary 1", status: "done" },
  });
  expect(seed.ok()).toBeTruthy();

  const meta1 = await request.get(`${state.backendUrl}/api/projects/${projectId}/chapters/meta?limit=1`);
  expect(meta1.ok()).toBeTruthy();
  const meta1Json = (await meta1.json()) as ApiOk<{
    chapters: Array<Record<string, unknown>>;
    next_cursor: number | null;
    has_more: boolean;
    returned: number;
    total: number;
  }>;
  expect(meta1Json.data.returned).toBe(1);
  expect(meta1Json.data.total).toBe(2);
  expect(meta1Json.data.has_more).toBe(true);
  expect(meta1Json.data.next_cursor).toBe(1);
  const first = meta1Json.data.chapters[0] ?? {};
  expect(first.id).toBe(chapter1!.id);
  expect(first.has_plan).toBe(true);
  expect(first.has_summary).toBe(true);
  expect(first.has_content).toBe(true);
  expect(Object.prototype.hasOwnProperty.call(first, "plan")).toBe(false);
  expect(Object.prototype.hasOwnProperty.call(first, "summary")).toBe(false);
  expect(Object.prototype.hasOwnProperty.call(first, "content_md")).toBe(false);

  const meta2 = await request.get(`${state.backendUrl}/api/projects/${projectId}/chapters/meta?limit=1&cursor=1`);
  expect(meta2.ok()).toBeTruthy();
  const meta2Json = (await meta2.json()) as ApiOk<{
    chapters: Array<Record<string, unknown>>;
    next_cursor: number | null;
    has_more: boolean;
    returned: number;
    total: number;
  }>;
  expect(meta2Json.data.returned).toBe(1);
  expect(meta2Json.data.total).toBe(2);
  expect(meta2Json.data.has_more).toBe(false);
  expect(meta2Json.data.next_cursor).toBeNull();
  expect(meta2Json.data.chapters[0]?.has_content).toBe(false);
  expect(meta2Json.data.chapters[0]?.has_summary).toBe(false);

  const legacy = await request.get(`${state.backendUrl}/api/projects/${projectId}/chapters`);
  expect(legacy.ok()).toBeTruthy();
  const legacyJson = (await legacy.json()) as ApiOk<{ chapters: Array<Record<string, unknown>> }>;
  const legacyFirst = legacyJson.data.chapters.find((chapter) => chapter.id === chapter1!.id) ?? {};
  expect(legacyFirst.plan).toBe("Plan 1");
  expect(legacyFirst.summary).toBe("Summary 1");
  expect(legacyFirst.content_md).toBe("# C1");

  const detail = await request.get(`${state.backendUrl}/api/chapters/${chapter1!.id}`);
  expect(detail.ok()).toBeTruthy();
  const detailJson = (await detail.json()) as ApiOk<{ chapter: Record<string, unknown> }>;
  expect(detailJson.data.chapter.plan).toBe("Plan 1");
  expect(detailJson.data.chapter.summary).toBe("Summary 1");
  expect(detailJson.data.chapter.content_md).toBe("# C1");
});
