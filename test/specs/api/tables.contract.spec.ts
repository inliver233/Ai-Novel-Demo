import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };
type ApiErr = { ok: false; error: { code: string; message: string; details: Record<string, unknown> | null }; request_id: string };

test("api: project tables CRUD + schema validation (contract)", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const createTable = await request.post(`${state.backendUrl}/api/projects/${projectId}/tables`, {
    data: {
      table_key: "inventory",
      name: "Inventory",
      schema: {
        version: 1,
        columns: [
          { key: "item", type: "string", required: true, label: "物品" },
          { key: "qty", type: "number", required: false, label: "数量" },
        ],
      },
    },
  });
  expect(createTable.ok()).toBeTruthy();
  const createTableJson = (await createTable.json()) as ApiOk<{ table: { id: string; table_key: string; row_count: number } }>;
  const tableId = createTableJson.data.table.id;
  expect(createTableJson.data.table.table_key).toBe("inventory");
  expect(createTableJson.data.table.row_count).toBe(0);

  const listTables = await request.get(`${state.backendUrl}/api/projects/${projectId}/tables`);
  expect(listTables.ok()).toBeTruthy();
  const listTablesJson = (await listTables.json()) as ApiOk<{ tables: Array<{ id: string; table_key: string }> }>;
  expect(listTablesJson.data.tables.some((t) => t.id === tableId && t.table_key === "inventory")).toBe(true);

  const createRow = await request.post(`${state.backendUrl}/api/projects/${projectId}/tables/${tableId}/rows`, {
    data: { data: { item: "Apple", qty: 2 } },
  });
  expect(createRow.ok()).toBeTruthy();
  const createRowJson = (await createRow.json()) as ApiOk<{ row: { id: string; data: Record<string, unknown> } }>;
  const rowId = createRowJson.data.row.id;
  expect(createRowJson.data.row.data.item).toBe("Apple");

  const listRows1 = await request.get(`${state.backendUrl}/api/projects/${projectId}/tables/${tableId}/rows?limit=10`);
  expect(listRows1.ok()).toBeTruthy();
  const listRows1Json = (await listRows1.json()) as ApiOk<{ rows: Array<{ id: string }>; total: number }>;
  expect(listRows1Json.data.total).toBeGreaterThanOrEqual(1);
  expect(listRows1Json.data.rows.some((r) => r.id === rowId)).toBe(true);

  const updateRow = await request.put(`${state.backendUrl}/api/projects/${projectId}/tables/${tableId}/rows/${rowId}`, {
    data: { data: { item: "Apple", qty: 3 } },
  });
  expect(updateRow.ok()).toBeTruthy();

  const updateSchemaOk = await request.put(`${state.backendUrl}/api/projects/${projectId}/tables/${tableId}`, {
    data: {
      schema: {
        version: 1,
        columns: [
          { key: "item", type: "string", required: true, label: "物品" },
          { key: "qty", type: "number", required: false, label: "数量" },
          { key: "note", type: "md", required: false, label: "备注" },
        ],
      },
    },
  });
  expect(updateSchemaOk.ok()).toBeTruthy();

  const updateRow2 = await request.put(`${state.backendUrl}/api/projects/${projectId}/tables/${tableId}/rows/${rowId}`, {
    data: { data: { item: "Apple", qty: 3, note: "fresh" } },
  });
  expect(updateRow2.ok()).toBeTruthy();

  const updateSchemaBad = await request.put(`${state.backendUrl}/api/projects/${projectId}/tables/${tableId}`, {
    data: { schema: { version: 1, columns: [{ key: "qty", type: "number", required: false }] } },
  });
  expect(updateSchemaBad.ok()).toBeFalsy();
  expect(updateSchemaBad.status()).toBe(400);
  const updateSchemaBadJson = (await updateSchemaBad.json()) as ApiErr;
  expect(updateSchemaBadJson.ok).toBe(false);
  expect(updateSchemaBadJson.error.code).toBe("VALIDATION_ERROR");

  const deleteRow = await request.delete(`${state.backendUrl}/api/projects/${projectId}/tables/${tableId}/rows/${rowId}`);
  expect(deleteRow.ok()).toBeTruthy();

  const deleteTable = await request.delete(`${state.backendUrl}/api/projects/${projectId}/tables/${tableId}`);
  expect(deleteTable.ok()).toBeTruthy();

  // Must not leak api keys or secrets (bootstrapProject uses "test-key").
  const raw = JSON.stringify({ createTableJson, listTablesJson, createRowJson });
  expect(raw).not.toContain("test-key");
  expect(raw).not.toMatch(/sk-[a-zA-Z0-9]{10,}/);
});

