import fs from "node:fs/promises";

import { test, expect, waitForWorldbookEntryCardsLoaded } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test.use({ acceptDownloads: true });

test("ui: worldbook import/export json (dry_run + apply)", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries`, {
    data: {
      title: "Dragon",
      content_md: "Fire.",
      enabled: true,
      constant: false,
      keywords: ["dragon"],
      exclude_recursion: false,
      prevent_recursion: false,
      char_limit: 12000,
      priority: "important",
    },
  });
  expect(create.ok()).toBeTruthy();

  await page.goto(`/projects/${projectId}/worldbook`);
  await waitForWorldbookEntryCardsLoaded(page, { minCount: 1 });
  await expect(page.getByText("Dragon", { exact: true })).toBeVisible();

  const download = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "导出 JSON", exact: true }).click(),
  ]).then(([d]) => d);

  const exportPath = test.info().outputPath(download.suggestedFilename());
  await download.saveAs(exportPath);
  const exportedRaw = await fs.readFile(exportPath, "utf-8");
  const exported = JSON.parse(exportedRaw) as {
    schema_version: string;
    entries: Array<Record<string, unknown>>;
  };
  expect(exported.schema_version).toBe("worldbook_export_all_v1");
  expect(exported.entries.some((e) => String(e.title || "") === "Dragon")).toBeTruthy();

  const importObj = {
    schema_version: exported.schema_version,
    entries: [
      {
        title: "Dragon",
        content_md: "Fire v2.",
        enabled: true,
        constant: false,
        keywords: ["dragon"],
        exclude_recursion: false,
        prevent_recursion: false,
        char_limit: 12000,
        priority: "important",
      },
      {
        title: "Castle",
        content_md: "Stone.",
        enabled: true,
        constant: false,
        keywords: ["castle"],
        exclude_recursion: false,
        prevent_recursion: false,
        char_limit: 12000,
        priority: "important",
      },
    ],
  };

  const importPath = test.info().outputPath("worldbook_import.json");
  await fs.writeFile(importPath, JSON.stringify(importObj, null, 2), "utf-8");

  await page.getByRole("button", { name: "导入 JSON", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "世界书导入", exact: true });
  await expect(drawer).toBeVisible();

  await drawer.getByLabel("导入 JSON 文件", { exact: true }).setInputFiles(importPath);
  await expect(drawer.getByText("已选择: worldbook_import.json", { exact: true })).toBeVisible();

  await drawer.getByRole("button", { name: "dry_run 预览", exact: true }).click();
  await expect(drawer.getByText("dry_run: true | mode: merge", { exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(drawer.getByText(/created:\s*1/)).toBeVisible();
  await expect(drawer.getByText(/updated:\s*1/)).toBeVisible();

  await drawer.getByRole("button", { name: "应用导入", exact: true }).click();
  await expect(drawer).toBeHidden();

  await expect(page.getByText("Castle", { exact: true })).toBeVisible({ timeout: 60_000 });
});
