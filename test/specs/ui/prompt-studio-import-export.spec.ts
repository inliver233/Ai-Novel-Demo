import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

test("ui: prompt studio export -> import -> new preset appears", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  await page.goto(`/projects/${projectId}/prompt-studio`);
  await expect(page.getByText("提示词工作室（beta）")).toBeVisible();

  // Pick a preset with chapter_generate enabled so export is meaningful.
  await page.getByRole("button", { name: /chapter_generate/ }).first().click();

  const exportResp = page.waitForResponse((resp) => {
    return resp.request().method() === "GET" && resp.url().includes("/api/prompt_presets/") && resp.url().endsWith("/export");
  });
  await page.getByRole("button", { name: "导出", exact: true }).click();

  const resp = await exportResp;
  expect(resp.ok()).toBeTruthy();
  const exportJson = (await resp.json()) as { ok: boolean; data?: { export?: any } };
  expect(exportJson.ok).toBe(true);
  expect(exportJson.data?.export).toBeTruthy();

  const exported = exportJson.data!.export as { preset?: { name?: string }; blocks?: unknown };
  const importedName = `E2E Imported Preset ${Date.now()}`;
  if (!exported.preset || typeof exported.preset !== "object") throw new Error("Export payload missing preset");
  exported.preset.name = importedName;

  const importResp = page.waitForResponse((r) => r.request().method() === "POST" && r.url().endsWith(`/api/projects/${projectId}/prompt_presets/import`));

  const fileInput = page.getByTestId("prompt-studio-import-file");
  await fileInput.setInputFiles({
    name: "preset.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(exported, null, 2), "utf-8"),
  });

  const imp = await importResp;
  expect(imp.ok()).toBeTruthy();

  await expect(page.getByText("已导入")).toBeVisible();
  await expect(page.getByRole("button", { name: new RegExp(importedName) })).toBeVisible();
});
