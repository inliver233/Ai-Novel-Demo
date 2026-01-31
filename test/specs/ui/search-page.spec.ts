import { test, expect, waitForWorldbookEntryCardsLoaded } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: global search hits multi-sources and can jump", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const token = `e2esearch${Date.now()}`;
  const characterName = `E2E Search Char ${Date.now()}`;
  const worldbookTitle = `E2E Search WB ${Date.now()}`;

  const charRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/characters`, {
    data: {
      name: characterName,
      role: "test",
      profile: `profile ${token}`,
      notes: `notes ${token}`,
    },
  });
  expect(charRes.ok()).toBeTruthy();

  const wbRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries`, {
    data: {
      title: worldbookTitle,
      content_md: `E2E worldbook content ${token}`,
      enabled: true,
      constant: false,
      keywords: [token],
      exclude_recursion: false,
      prevent_recursion: false,
      char_limit: 12000,
      priority: "important",
    },
  });
  expect(wbRes.ok()).toBeTruthy();

  const createChapterRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E Search Chapter", plan: "" },
  });
  expect(createChapterRes.ok()).toBeTruthy();
  const createChapterJson = (await createChapterRes.json()) as { ok: boolean; data: { chapter: { id: string } } };
  const chapterId = createChapterJson.data.chapter.id;

  const chapterContent = `# E2E Search Chapter\n\n${token}\n`;
  const putRes = await request.put(`${state.backendUrl}/api/chapters/${chapterId}`, {
    data: { content_md: chapterContent, status: "drafting" },
  });
  expect(putRes.ok()).toBeTruthy();

  const runSearch = async () => {
    await page.goto(`/projects/${projectId}/search`);
    const queryInput = page.getByLabel("search_query", { exact: true });
    await expect(queryInput).toBeVisible();

    // Atelier UI guardrails (avoid default blue / missing btn base class regressions).
    const clearBtn = page.getByLabel("search_clear", { exact: true });
    await expect(clearBtn).toHaveClass(/\bbtn\b/);
    await expect(clearBtn).toHaveClass(/\bbtn-secondary\b/);

    const submitBtn = page.getByLabel("search_submit", { exact: true });
    await expect(submitBtn).toHaveClass(/\bbtn\b/);
    await expect(submitBtn).toHaveClass(/\bbtn-primary\b/);

    const chapterSource = page.getByLabel("search_source_chapter", { exact: true });
    await expect(chapterSource).toHaveClass(/\bcheckbox\b/);
    await expect(chapterSource).toHaveAttribute("name", "search_source_chapter");

    await queryInput.fill(token);
    await page.getByLabel("search_submit", { exact: true }).click();

    const results = page.getByLabel("search_results", { exact: true });
    await expect.poll(async () => await results.locator(".panel").count()).toBeGreaterThanOrEqual(3);

    const loadMore = page.getByLabel("search_load_more", { exact: true });
    if ((await loadMore.count()) > 0) {
      await expect(loadMore).toHaveClass(/\bbtn\b/);
      await expect(loadMore).toHaveClass(/\bbtn-secondary\b/);
    }
    return results;
  };

  // chapter -> writing
  const results1 = await runSearch();
  const chapterCard = results1.locator(".panel").filter({ hasText: "chapter" }).first();
  await expect(chapterCard).toBeVisible();
  await expect(chapterCard.getByLabel("search_copy_id", { exact: true })).toHaveClass(/\bbtn\b/);
  await expect(chapterCard.getByLabel("search_copy_id", { exact: true })).toHaveClass(/\bbtn-secondary\b/);
  await expect(chapterCard.getByLabel("search_jump", { exact: true })).toHaveClass(/\bbtn\b/);
  await expect(chapterCard.getByLabel("search_jump", { exact: true })).toHaveClass(/\bbtn-primary\b/);
  await chapterCard.getByLabel("search_jump", { exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/writing\\?chapterId=${chapterId}$`));
  await expect(page.locator('textarea[name="content_md"]')).toContainText(token);

  // worldbook -> worldbook filtered list
  const results2 = await runSearch();
  const wbCard = results2.locator(".panel").filter({ hasText: "worldbook_entry" }).first();
  await expect(wbCard).toBeVisible();
  await wbCard.getByLabel("search_jump", { exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/worldbook$`));
  await waitForWorldbookEntryCardsLoaded(page, { minCount: 1 });
  await expect(page.getByRole("button", { name: new RegExp(worldbookTitle) }).first()).toBeVisible();

  // character -> characters list
  const results3 = await runSearch();
  const characterCard = results3.locator(".panel").filter({ hasText: "character" }).first();
  await expect(characterCard).toBeVisible();
  await characterCard.getByLabel("search_jump", { exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/characters$`));
  await expect(page.getByText(characterName, { exact: true })).toBeVisible();
});
