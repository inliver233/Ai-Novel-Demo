import { test, expect, waitForWorldbookEntryCardsLoaded } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: worldbook paginates large entry lists (perf guard)", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const entryCount = 220;
  const entries = Array.from({ length: entryCount }, (_, i) => ({
    title: `E2E Large WB ${i}`,
    content_md: `content ${i}`,
    enabled: true,
    constant: false,
    keywords: [`kw${i}`],
    exclude_recursion: false,
    prevent_recursion: false,
    char_limit: 12000,
    priority: "important",
  }));

  const importRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries/import_all`, {
    data: {
      schema_version: "worldbook_export_all_v1",
      dry_run: false,
      mode: "merge",
      entries,
    },
  });
  expect(importRes.ok()).toBeTruthy();

  await page.goto(`/projects/${projectId}/worldbook`);
  await expect(page.getByText("条目列表", { exact: true })).toBeVisible();

  const cards = await waitForWorldbookEntryCardsLoaded(page, { minCount: 1 });
  const initialCount = await cards.count();
  expect(initialCount).toBeGreaterThan(0);
  expect(initialCount).toBeLessThan(entryCount);

  await expect(page.getByText(/^第 1\/\d+ 页$/)).toBeVisible();

  const nextPage = page.getByLabel("worldbook_load_more", { exact: true });
  await expect(nextPage).toBeEnabled();
  await nextPage.click();

  await expect(page.getByText(/^第 2\/\d+ 页$/)).toBeVisible();
  await expect(page.getByLabel("worldbook_page_prev", { exact: true })).toBeEnabled();
});
