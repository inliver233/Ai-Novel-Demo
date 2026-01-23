import { test, expect, waitForWorldbookBulkSelectedCount, waitForWorldbookEntryCardsLoaded } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("ui: worldbook bulk disable (selection + confirm)", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  for (const title of ["E2E WB Bulk A", "E2E WB Bulk B"]) {
    const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries`, {
      data: {
        title,
        content_md: `${title} content`,
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
  }

  await page.goto(`/projects/${projectId}/worldbook`);
  await waitForWorldbookEntryCardsLoaded(page, { minCount: 1 });
  await expect(page.getByText("E2E WB Bulk A", { exact: true })).toBeVisible();

  await page.getByLabel("worldbook_bulk_mode", { exact: true }).check();
  await waitForWorldbookBulkSelectedCount(page, 0);
  await page.getByText("E2E WB Bulk A", { exact: true }).click();
  await page.getByText("E2E WB Bulk B", { exact: true }).click();
  await waitForWorldbookBulkSelectedCount(page, 2);

  const bulkUpdateRes = page.waitForResponse((res) => {
    if (res.request().method() !== "POST") return false;
    return res.url().includes(`/api/projects/${projectId}/worldbook_entries/bulk_update`);
  });
  await page.getByLabel("worldbook_bulk_disable", { exact: true }).click();
  await expect(page.getByText("批量停用条目？", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "确认", exact: true }).click();
  await bulkUpdateRes;

  const listRes = await request.get(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries`);
  expect(listRes.ok()).toBeTruthy();
  const listJson = (await listRes.json()) as ApiOk<{ worldbook_entries: Array<{ title: string; enabled: boolean }> }>;
  const byTitle = new Map(listJson.data.worldbook_entries.map((e) => [e.title, e]));
  expect(byTitle.get("E2E WB Bulk A")?.enabled).toBe(false);
  expect(byTitle.get("E2E WB Bulk B")?.enabled).toBe(false);
});
