import { test, expect } from "../../lib/ui-test";

import type { APIRequestContext } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

async function seedTableForInjection(request: APIRequestContext, projectId: string): Promise<void> {
  const state = loadState();

  const createRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/tables`, {
    data: {
      table_key: "e2e_money",
      name: "E2E Money",
      schema: {
        version: 1,
        columns: [
          { key: "key", type: "string", label: "Key", required: true },
          { key: "value", type: "string", label: "Value", required: false },
        ],
      },
    },
  });
  if (!createRes.ok()) throw new Error(`Failed to create table: ${createRes.status()} ${await createRes.text()}`);
  const createJson = (await createRes.json()) as ApiOk<{ table: { id: string } }>;
  if (!createJson.ok) throw new Error("Create table response not ok");
  const tableId = createJson.data.table.id;

  const row1Res = await request.post(`${state.backendUrl}/api/projects/${projectId}/tables/${tableId}/rows`, {
    data: { data: { key: "gold", value: "100" } },
  });
  if (!row1Res.ok()) throw new Error(`Failed to create row1: ${row1Res.status()} ${await row1Res.text()}`);

  const row2Res = await request.post(`${state.backendUrl}/api/projects/${projectId}/tables/${tableId}/rows`, {
    data: { data: { key: "gem", value: "2" } },
  });
  if (!row2Res.ok()) throw new Error(`Failed to create row2: ${row2Res.status()} ${await row2Res.text()}`);
}

test("ui: tables injection appears in ContextPreview + prompt_preview (chapter_generate)", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);
  await seedTableForInjection(request, projectId);

  await page.goto(`/projects/${projectId}/writing`);

  await expect(page.getByRole("button", { name: "新增章节" })).toBeVisible();
  await page.getByRole("button", { name: "新增章节" }).click();
  await expect(page.getByRole("dialog", { name: "新增章节" })).toBeVisible();
  await page.locator('input[name="number"]').fill("1");
  await page.locator('input[name="title"]').fill("E2E 第一章");
  await page.locator('textarea[name="plan"]').fill("gold");
  await page.getByRole("button", { name: "创建", exact: true }).click();

  await page.getByRole("button", { name: "AI 生成", exact: true }).click();
  const genDrawer = page.getByRole("dialog", { name: "AI 生成", exact: true });
  await expect(genDrawer).toBeVisible();

  const tablesToggle = genDrawer.getByRole("checkbox", { name: "表格系统（tables）", exact: true });
  await expect(tablesToggle).toBeVisible();
  await expect(tablesToggle).toBeChecked();
  await genDrawer.getByLabel("memory_query_text", { exact: true }).fill("gold");
  await genDrawer.getByRole("button", { name: "关闭", exact: true }).click();

  await page.getByRole("button", { name: "上下文预览", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "上下文预览", exact: true });
  await expect(dialog).toBeVisible();

  const tablesTextSummary = dialog.locator("summary", { hasText: "tables.text_md" });
  await tablesTextSummary.click();
  const tablesDetails = tablesTextSummary.locator("..");
  await expect(tablesDetails).toHaveAttribute("open", "");
  await expect(tablesDetails).toContainText("<TABLES>");
  await expect(tablesDetails).toContainText("gold");

  // Contract: prompt_preview must include the same sys.memory.tables text as memory/preview.
  const state = loadState();
  const previewRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/memory/preview`, {
    data: {
      query_text: "gold",
      section_enabled: { tables: true },
      budget_overrides: { tables: 900 },
    },
  });
  if (!previewRes.ok()) throw new Error(`memory/preview failed: ${previewRes.status()} ${await previewRes.text()}`);
  const previewJson = (await previewRes.json()) as ApiOk<Record<string, unknown>>;
  if (!previewJson.ok) throw new Error("memory/preview response not ok");
  const pack = previewJson.data as Record<string, unknown>;
  const tablesPack = (pack.tables ?? {}) as Record<string, unknown>;
  const tablesTextMd = typeof tablesPack.text_md === "string" ? tablesPack.text_md : "";
  expect(tablesTextMd).toContain("<TABLES>");

  const promptRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/prompt_preview`, {
    data: {
      task: "chapter_generate",
      values: {
        memory: pack,
        memory_injection_enabled: true,
        context_optimizer_enabled: false,
      },
    },
  });
  if (!promptRes.ok()) throw new Error(`prompt_preview failed: ${promptRes.status()} ${await promptRes.text()}`);
  const promptJson = (await promptRes.json()) as ApiOk<{ preview: { blocks: Array<{ identifier: string; text: string }> } }>;
  if (!promptJson.ok) throw new Error("prompt_preview response not ok");
  const blocks = promptJson.data.preview.blocks;
  const tablesBlock = blocks.find((b) => b.identifier === "sys.memory.tables");
  expect(tablesBlock?.text ?? "").toContain("<TABLES>");
  expect(tablesBlock?.text ?? "").toBe(tablesTextMd);
});

