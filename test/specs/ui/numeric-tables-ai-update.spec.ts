import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("ui: numeric tables ai_update -> TaskCenter apply/rollback", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  await page.goto(`/projects/${projectId}/numeric-tables`);

  const tableSelect = page.getByLabel("tables_select", { exact: true });
  await expect(tableSelect).toBeVisible();
  const moneyOptions = tableSelect.getByRole("option", { name: /tbl_money/ });
  await expect(moneyOptions).toHaveCount(1, { timeout: 60_000 });
  const moneyTableId = await moneyOptions.first().getAttribute("value");
  if (!moneyTableId) throw new Error("Missing tbl_money option value");
  await tableSelect.selectOption(moneyTableId);

  const goldRowId = await (async () => {
    const res = await request.get(`${state.backendUrl}/api/projects/${projectId}/tables/${moneyTableId}/rows?limit=200`);
    if (!res.ok()) throw new Error(`Failed to list rows: ${res.status()}`);
    const json = (await res.json()) as ApiOk<{ rows: Array<{ id: string; data?: Record<string, unknown> }>; total: number }>;
    const rows = Array.isArray(json.data?.rows) ? json.data.rows : [];
    const gold = rows.find((r) => String(r.data?.key ?? "") === "gold");
    if (!gold?.id) throw new Error("Missing gold row from seeded numeric table tbl_money");
    return gold.id;
  })();

  const goldKeyInput = page.locator(`input[aria-label="cell_${goldRowId}_key"]`);
  await expect(goldKeyInput).toHaveValue("gold", { timeout: 60_000 });
  const goldValueInput = page.locator(`input[aria-label="cell_${goldRowId}_value"]`);
  const goldRow = goldKeyInput.locator("..").locator("..");

  await goldValueInput.fill("50");
  await goldRow.getByRole("button", { name: "保存", exact: true }).click();
  await expect(goldValueInput).toHaveValue("50", { timeout: 60_000 });

  await expect
    .poll(
      async () => {
        const res = await request.get(`${state.backendUrl}/api/projects/${projectId}/tables/${moneyTableId}/rows?limit=200`);
        if (!res.ok()) return "http_error";
        const json = (await res.json()) as ApiOk<{ rows: Array<{ id: string; data?: Record<string, unknown> }>; total: number }>;
        const row = (json.data?.rows || []).find((r) => r.id === goldRowId);
        const value = (row?.data as Record<string, unknown> | undefined)?.value;
        return String(value ?? "");
      },
      { timeout: 60_000 },
    )
    .toBe("50");

  await page.locator("summary", { hasText: "AI 更新（table_ai_update）" }).click();

  const aiTargetSelect = page.getByLabel("选择目标表 (numeric_tables_select_table)", { exact: true });
  await expect(aiTargetSelect).toBeVisible();
  const aiMoneyOptions = aiTargetSelect.getByRole("option", { name: /tbl_money/ });
  await expect(aiMoneyOptions).toHaveCount(1, { timeout: 60_000 });
  const aiMoneyTableId = await aiMoneyOptions.first().getAttribute("value");
  if (!aiMoneyTableId) throw new Error("Missing ai tbl_money option value");
  await aiTargetSelect.selectOption(aiMoneyTableId);

  await page.getByLabel("AI 更新 focus (numeric_tables_ai_focus)", { exact: true }).fill("E2E_TABLE_SET_GOLD_100");
  await page.getByLabel("创建 AI 更新任务 (numeric_tables_ai_schedule)", { exact: true }).click();

  const taskLink = page.getByRole("link", { name: /打开 Task Center（定位本次任务）/ }).first();
  await expect(taskLink).toBeVisible({ timeout: 60_000 });
  const href = await taskLink.getAttribute("href");
  if (!href) throw new Error("Missing task center link href");
  const m = href.match(/project_task_id=([^&]+)/);
  if (!m?.[1]) throw new Error(`Missing project_task_id in href: ${href}`);
  const taskId = decodeURIComponent(m[1]);

  await expect
    .poll(
      async () => {
        const res = await request.get(`${state.backendUrl}/api/tasks/${encodeURIComponent(taskId)}`);
        if (!res.ok()) return "http_error";
        const json = (await res.json()) as ApiOk<{ status: string }>;
        return String((json.data as { status?: string } | null | undefined)?.status ?? "");
      },
      { timeout: 60_000 },
    )
    .toBe("done");

  await page.goto(href);
  const projectTaskRow = page.getByRole("button", { name: new RegExp(taskId) }).first();
  await expect(projectTaskRow).toBeVisible({ timeout: 60_000 });
  await projectTaskRow.click();
  const apply = page.getByLabel("应用变更集 (taskcenter_changeset_apply)", { exact: true });
  const rollback = page.getByLabel("回滚变更集 (taskcenter_changeset_rollback)", { exact: true });
  await expect(apply).toBeVisible({ timeout: 60_000 });

  await expect(apply).toBeEnabled({ timeout: 60_000 });
  await apply.click();
  await expect(rollback).toBeEnabled({ timeout: 60_000 });

  await page.goto(`/projects/${projectId}/numeric-tables`);
  await tableSelect.selectOption(moneyTableId);
  await expect(goldValueInput).toHaveValue("100", { timeout: 60_000 });
  await expect
    .poll(
      async () => {
        const res = await request.get(`${state.backendUrl}/api/projects/${projectId}/tables/${moneyTableId}/rows?limit=200`);
        if (!res.ok()) return "http_error";
        const json = (await res.json()) as ApiOk<{ rows: Array<{ id: string; data?: Record<string, unknown> }>; total: number }>;
        const row = (json.data?.rows || []).find((r) => r.id === goldRowId);
        const value = (row?.data as Record<string, unknown> | undefined)?.value;
        return String(value ?? "");
      },
      { timeout: 60_000 },
    )
    .toBe("100");

  await page.goto(href);
  await expect(projectTaskRow).toBeVisible({ timeout: 60_000 });
  await projectTaskRow.click();
  await expect(rollback).toBeEnabled({ timeout: 60_000 });
  await rollback.click();
  await expect(rollback).toBeDisabled({ timeout: 60_000 });

  await page.goto(`/projects/${projectId}/numeric-tables`);
  await tableSelect.selectOption(moneyTableId);
  await expect(goldValueInput).toHaveValue("50", { timeout: 60_000 });
  await expect
    .poll(
      async () => {
        const res = await request.get(`${state.backendUrl}/api/projects/${projectId}/tables/${moneyTableId}/rows?limit=200`);
        if (!res.ok()) return "http_error";
        const json = (await res.json()) as ApiOk<{ rows: Array<{ id: string; data?: Record<string, unknown> }>; total: number }>;
        const row = (json.data?.rows || []).find((r) => r.id === goldRowId);
        const value = (row?.data as Record<string, unknown> | undefined)?.value;
        return String(value ?? "");
      },
      { timeout: 60_000 },
    )
    .toBe("50");
});
