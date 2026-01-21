import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("ui: prompt studio export_all -> import_all + category filter", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const categoryA = "E2E Cat A";
  const categoryB = "E2E Cat B";
  const presetAName = `E2E Cat A Preset ${Date.now()}`;
  const presetBName = `E2E Cat B Preset ${Date.now()}`;

  for (const [name, category] of [
    [presetAName, categoryA],
    [presetBName, categoryB],
  ]) {
    const res = await request.post(`${state.backendUrl}/api/projects/${projectId}/prompt_presets`, {
      data: { name, category, scope: "project", version: 1, active_for: [] },
    });
    expect(res.ok()).toBeTruthy();
  }

  await page.goto(`/projects/${projectId}/prompt-studio`);
  await expect(page.getByText("提示词工作室（beta）")).toBeVisible();

  await expect(page.getByRole("button", { name: presetAName })).toBeVisible();
  await expect(page.getByRole("button", { name: presetBName })).toBeVisible();

  const categorySelect = page.getByText("分类").locator("..").getByRole("combobox");
  await categorySelect.selectOption({ label: categoryA });
  await expect(page.getByRole("button", { name: presetAName })).toBeVisible();
  await expect(page.getByRole("button", { name: presetBName })).not.toBeVisible();

  await categorySelect.selectOption({ value: "__all__" });

  const exportResp = page.waitForResponse(
    (resp) =>
      resp.request().method() === "GET" &&
      resp.url().endsWith(`/api/projects/${projectId}/prompt_presets/export_all`) &&
      resp.ok(),
  );
  await page.getByRole("button", { name: "导出整套", exact: true }).click();
  await expect(page.getByText("已导出整套")).toBeVisible();

  const exported = (await (await exportResp).json()) as ApiOk<{ export: any }>;
  expect(exported.ok).toBe(true);
  expect(exported.data.export?.schema_version).toBe("prompt_presets_export_all_v1");

  const bulkPresetName = `E2E Bulk Preset ${Date.now()}`;
  const exportObj = exported.data.export as { schema_version: string; presets: any[] };
  exportObj.presets = Array.isArray(exportObj.presets) ? exportObj.presets : [];
  exportObj.presets.unshift({
    preset: { name: bulkPresetName, category: "E2E Bulk", scope: "project", version: 1, active_for: [] },
    blocks: [],
  });

  const dryRunResp = page.waitForResponse(
    (resp) =>
      resp.request().method() === "POST" &&
      resp.url().endsWith(`/api/projects/${projectId}/prompt_presets/import_all`) &&
      resp.ok(),
  );

  await page.getByTestId("prompt-studio-import-all-file").setInputFiles({
    name: "all.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(exportObj, null, 2), "utf-8"),
  });

  await dryRunResp;
  await expect(page.getByText("导入整套 PromptPresets（dry_run）")).toBeVisible();

  const applyResp = page.waitForResponse(
    (resp) =>
      resp.request().method() === "POST" &&
      resp.url().endsWith(`/api/projects/${projectId}/prompt_presets/import_all`) &&
      resp.ok(),
  );
  await page.getByRole("button", { name: "应用导入", exact: true }).click();
  await applyResp;

  await expect(page.getByText("已导入整套")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("button", { name: new RegExp(bulkPresetName) })).toBeVisible();
});
