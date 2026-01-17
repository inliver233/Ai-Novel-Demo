import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };
type ApiErr = { ok: false; error: { code: string; message: string; details?: Record<string, unknown> }; request_id: string };

test("api: worldbook bulk_update + duplicate + bulk_delete contract", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create1 = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries`, {
    data: {
      title: "E2E WB Bulk 1",
      content_md: "dragon",
      enabled: true,
      constant: false,
      keywords: ["dragon"],
      exclude_recursion: false,
      prevent_recursion: false,
      char_limit: 12000,
      priority: "important",
    },
  });
  expect(create1.ok()).toBeTruthy();
  const create1Json = (await create1.json()) as ApiOk<{ worldbook_entry: { id: string } }>;
  const id1 = create1Json.data.worldbook_entry.id;

  const create2 = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries`, {
    data: {
      title: "E2E WB Bulk 2",
      content_md: "wolf",
      enabled: true,
      constant: false,
      keywords: ["wolf"],
      exclude_recursion: false,
      prevent_recursion: false,
      char_limit: 12000,
      priority: "important",
    },
  });
  expect(create2.ok()).toBeTruthy();
  const create2Json = (await create2.json()) as ApiOk<{ worldbook_entry: { id: string } }>;
  const id2 = create2Json.data.worldbook_entry.id;

  const bulkUpdate = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries/bulk_update`, {
    data: {
      entry_ids: [id1, id2],
      enabled: false,
      constant: true,
      prevent_recursion: true,
      priority: "must",
      char_limit: 1234,
    },
  });
  expect(bulkUpdate.ok()).toBeTruthy();
  const bulkUpdateJson = (await bulkUpdate.json()) as ApiOk<{
    worldbook_entries: Array<{
      id: string;
      enabled: boolean;
      constant: boolean;
      prevent_recursion: boolean;
      priority: string;
      char_limit: number;
    }>;
  }>;
  expect(bulkUpdateJson.data.worldbook_entries).toHaveLength(2);
  expect(bulkUpdateJson.data.worldbook_entries[0]?.id).toBe(id1);
  expect(bulkUpdateJson.data.worldbook_entries[1]?.id).toBe(id2);
  for (const e of bulkUpdateJson.data.worldbook_entries) {
    expect(e.enabled).toBe(false);
    expect(e.constant).toBe(true);
    expect(e.prevent_recursion).toBe(true);
    expect(e.priority).toBe("must");
    expect(e.char_limit).toBe(1234);
  }

  const duplicate = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries/duplicate`, {
    data: { entry_ids: [id1] },
  });
  expect(duplicate.ok()).toBeTruthy();
  const duplicateJson = (await duplicate.json()) as ApiOk<{ worldbook_entries: Array<{ id: string; title: string; enabled: boolean }> }>;
  expect(duplicateJson.data.worldbook_entries).toHaveLength(1);
  const dup = duplicateJson.data.worldbook_entries[0]!;
  expect(dup.id).not.toBe(id1);
  expect(dup.title).toContain("E2E WB Bulk 1");
  expect(dup.enabled).toBe(false);

  const bulkDelete = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries/bulk_delete`, {
    data: { entry_ids: [id1, id2] },
  });
  expect(bulkDelete.ok()).toBeTruthy();
  const bulkDeleteJson = (await bulkDelete.json()) as ApiOk<{ deleted_ids: string[] }>;
  expect(bulkDeleteJson.data.deleted_ids).toEqual([id1, id2]);

  const list = await request.get(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries`);
  expect(list.ok()).toBeTruthy();
  const listJson = (await list.json()) as ApiOk<{ worldbook_entries: Array<{ id: string }> }>;
  const ids = new Set(listJson.data.worldbook_entries.map((e) => e.id));
  expect(ids.has(id1)).toBe(false);
  expect(ids.has(id2)).toBe(false);
  expect(ids.has(dup.id)).toBe(true);

  const missingId = "missing-worldbook-entry-id";
  const missing = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries/bulk_update`, {
    data: { entry_ids: [missingId], enabled: false },
  });
  expect(missing.ok()).toBe(false);
  expect(missing.status()).toBe(404);
  const missingJson = (await missing.json()) as ApiErr;
  expect(missingJson.ok).toBe(false);
  expect(missingJson.error.code).toBe("NOT_FOUND");
  const missingIds = (missingJson.error.details?.missing_ids as unknown[]) ?? [];
  expect(missingIds).toContain(missingId);
});

