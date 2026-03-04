import crypto from "crypto";

import { test, expect, waitForWorldbookEntryCardsLoaded } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: global search hits multi-sources and can jump", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const token = `e2esearch${Date.now()}`;
  const characterName = `E2E Search Char ${Date.now()}`;
  const worldbookTitle = `E2E Search WB ${Date.now()}`;
  const importFilename = `e2e-import-${token}.txt`;
  const tableName = `E2E Search Table ${Date.now()}`;
  const tableKey = `e2e_search_${Date.now()}`;

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

  const outlineRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/outlines`, {
    data: { title: "E2E Search Outline", content_md: `Outline ${token}` },
  });
  expect(outlineRes.ok()).toBeTruthy();
  const outlineJson = (await outlineRes.json()) as { ok: boolean; data: { outline: { id: string } } };
  const outlineId = outlineJson.data.outline.id;

  const createChapterRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E Search Chapter", plan: "", status: "done" },
  });
  expect(createChapterRes.ok()).toBeTruthy();
  const createChapterJson = (await createChapterRes.json()) as { ok: boolean; data: { chapter: { id: string } } };
  const chapterId = createChapterJson.data.chapter.id;

  const chapterContent = `# E2E Search Chapter\n\n${token}\n`;
  const putRes = await request.put(`${state.backendUrl}/api/chapters/${chapterId}`, {
    data: { content_md: chapterContent, status: "done" },
  });
  expect(putRes.ok()).toBeTruthy();

  const storyRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/story_memories`, {
    data: {
      chapter_id: chapterId,
      memory_type: "event",
      title: "E2E story_memory",
      content: `Story memory ${token}`,
      importance_score: 0.1,
      tags: [token],
      story_timeline: 0,
      text_position: -1,
      text_length: 0,
      is_foreshadow: false,
    },
  });
  expect(storyRes.ok()).toBeTruthy();

  const importRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/imports`, {
    data: { filename: importFilename, content_text: `import ${token}`, content_type: "txt" },
  });
  expect(importRes.ok()).toBeTruthy();
  const importJson = (await importRes.json()) as { ok: boolean; data: { document: { id: string } } };
  const importDocId = importJson.data.document.id;

  const tableRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/tables`, {
    data: {
      table_key: tableKey,
      name: tableName,
      schema: {
        version: 1,
        columns: [
          { key: "key", type: "string", label: "Key", required: true },
          { key: "value", type: "string", label: "Value", required: false },
        ],
      },
    },
  });
  expect(tableRes.ok()).toBeTruthy();
  const tableJson = (await tableRes.json()) as { ok: boolean; data: { table: { id: string } } };
  const tableId = tableJson.data.table.id;

  const rowRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/tables/${encodeURIComponent(tableId)}/rows`, {
    data: { data: { key: token, value: `row ${token}` } },
  });
  expect(rowRes.ok()).toBeTruthy();

  const aliceId = crypto.randomUUID();
  const bobId = crypto.randomUUID();
  const relId = crypto.randomUUID();
  const evidenceId = crypto.randomUUID();
  const memKey = `e2e-search-mem-${crypto.randomUUID().slice(0, 12)}`;
  const relationQuote = `E2E quote ${token}`;

  const propose = await request.post(`${state.backendUrl}/api/chapters/${chapterId}/memory/propose`, {
    data: {
      schema_version: "memory_update_v1",
      idempotency_key: memKey,
      title: "E2E search seed structured memory",
      ops: [
        {
          op: "upsert",
          target_table: "entities",
          target_id: aliceId,
          after: { entity_type: "character", name: "Alice", attributes: { tags: [token] } },
        },
        {
          op: "upsert",
          target_table: "entities",
          target_id: bobId,
          after: { entity_type: "character", name: "Bob", attributes: { tags: [token] } },
        },
        {
          op: "upsert",
          target_table: "relations",
          target_id: relId,
          after: { from_entity_id: aliceId, to_entity_id: bobId, relation_type: "friend", description_md: `desc ${token}` },
        },
        {
          op: "upsert",
          target_table: "evidence",
          target_id: evidenceId,
          after: { source_type: "relation", source_id: relId, quote_md: relationQuote },
        },
      ],
    },
  });
  expect(propose.ok()).toBeTruthy();
  const proposeJson = (await propose.json()) as { ok: boolean; data: { change_set: { id: string } } };
  const changeSetId = proposeJson.data.change_set.id;

  const apply = await request.post(`${state.backendUrl}/api/memory_change_sets/${changeSetId}/apply`);
  expect(apply.ok()).toBeTruthy();

  // Trigger a rebuild after all data is present (tables/structured memory/imports do not schedule search rebuild directly).
  const triggerRes = await request.put(`${state.backendUrl}/api/projects/${projectId}/outlines/${encodeURIComponent(outlineId)}`, {
    data: { content_md: `Outline ${token} trigger` },
  });
  expect(triggerRes.ok()).toBeTruthy();

  const expectedTypes = [
    "chapter",
    "outline",
    "worldbook_entry",
    "character",
    "story_memory",
    "source_document",
    "project_table_row",
    "memory_entity",
    "memory_relation",
    "memory_evidence",
  ];
  await expect
    .poll(
      async () => {
        const q = await request.post(`${state.backendUrl}/api/projects/${projectId}/search/query`, {
          data: { q: token, limit: 200, offset: 0 },
        });
        if (!q.ok()) return false;
        const j = (await q.json()) as { ok: boolean; data: { items?: Array<{ source_type: string }> } };
        const items = j.data.items ?? [];
        const types = new Set(items.map((it) => String(it.source_type || "")));
        return expectedTypes.every((t) => types.has(t));
      },
      { timeout: 60_000 },
    )
    .toBe(true);

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

    const outlineSource = page.getByLabel("search_source_outline", { exact: true });
    await expect(outlineSource).toHaveClass(/\bcheckbox\b/);
    await expect(outlineSource).toHaveAttribute("name", "search_source_outline");

    await expect(page.getByLabel("search_source_source_document", { exact: true })).toHaveClass(/\bcheckbox\b/);
    await expect(page.getByLabel("search_source_project_table_row", { exact: true })).toHaveClass(/\bcheckbox\b/);
    await expect(page.getByLabel("search_source_memory_entity", { exact: true })).toHaveClass(/\bcheckbox\b/);
    await expect(page.getByLabel("search_source_memory_relation", { exact: true })).toHaveClass(/\bcheckbox\b/);
    await expect(page.getByLabel("search_source_memory_evidence", { exact: true })).toHaveClass(/\bcheckbox\b/);

    await queryInput.fill(token);
    await page.getByLabel("search_submit", { exact: true }).click();

    const results = page.getByLabel("search_results", { exact: true });
    await expect.poll(async () => await results.locator(".panel").count()).toBeGreaterThanOrEqual(expectedTypes.length);

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
  await expect(chapterCard.getByLabel("search_copy_locator", { exact: true })).toHaveClass(/\bbtn\b/);
  await expect(chapterCard.getByLabel("search_copy_locator", { exact: true })).toHaveClass(/\bbtn-secondary\b/);
  await expect(chapterCard.getByLabel("search_copy_locator", { exact: true })).toBeEnabled();
  await expect(chapterCard.getByLabel("search_jump", { exact: true })).toHaveClass(/\bbtn\b/);
  await expect(chapterCard.getByLabel("search_jump", { exact: true })).toHaveClass(/\bbtn-primary\b/);
  await chapterCard.getByLabel("search_jump", { exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/writing\\?chapterId=${chapterId}$`));
  await expect(page.locator('textarea[name="content_md"]')).toContainText(token);

  // outline -> outline page
  const resultsOutline = await runSearch();
  const outlineCard = resultsOutline.locator(".panel").filter({ hasText: "outline" }).first();
  await expect(outlineCard).toBeVisible();
  await outlineCard.getByLabel("search_jump", { exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/outline$`));

  // worldbook -> worldbook filtered list
  const results2 = await runSearch();
  const wbCard = results2.locator(".panel").filter({ hasText: "worldbook_entry" }).first();
  await expect(wbCard).toBeVisible();
  await wbCard.getByLabel("search_jump", { exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/worldbook(?:\\?.*)?$`));
  await waitForWorldbookEntryCardsLoaded(page, { minCount: 1 });
  await expect(page.getByRole("button", { name: new RegExp(worldbookTitle) }).first()).toBeVisible();

  // character -> characters list
  const results3 = await runSearch();
  const characterCard = results3.locator(".panel").filter({ hasText: characterName }).first();
  await expect(characterCard).toBeVisible();
  await characterCard.getByLabel("search_jump", { exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/characters$`));
  await expect(page.getByText(characterName, { exact: true })).toBeVisible();

  // story_memory -> chapter analysis
  const resultsMem = await runSearch();
  const memCard = resultsMem.locator(".panel").filter({ hasText: "story_memory" }).first();
  await expect(memCard).toBeVisible();
  await memCard.getByLabel("search_jump", { exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/chapter-analysis\\?chapterId=${chapterId}$`));

  // source_document -> import page (auto-open docId)
  const resultsImport = await runSearch();
  const importCard = resultsImport.locator(".panel").filter({ hasText: "source_document" }).first();
  await expect(importCard).toBeVisible();
  await importCard.getByLabel("search_jump", { exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/import\\?docId=${importDocId}$`));
  await expect(page.getByRole("button", { name: new RegExp(importFilename.replaceAll(".", "\\.")) }).first()).toBeVisible();

  // project_table_row -> numeric tables
  const resultsTables = await runSearch();
  const tableCard = resultsTables.locator(".panel").filter({ hasText: "project_table_row" }).first();
  await expect(tableCard).toBeVisible();
  await tableCard.getByLabel("search_jump", { exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/numeric-tables$`));
  const tablesSelect = page.getByLabel("tables_select", { exact: true });
  await expect(tablesSelect).toBeVisible({ timeout: 60_000 });
  await expect(tablesSelect.getByRole("option", { name: new RegExp(tableName) })).toHaveCount(1, { timeout: 60_000 });
  await tablesSelect.selectOption(tableId);

  const tableRowId = await (async () => {
    const res = await request.get(
      `${state.backendUrl}/api/projects/${projectId}/tables/${encodeURIComponent(tableId)}/rows?limit=200`,
    );
    if (!res.ok()) throw new Error(`Failed to list table rows after search jump: ${res.status()}`);
    const json = (await res.json()) as {
      ok: boolean;
      data: { rows: Array<{ id: string; data?: Record<string, unknown> }>; total: number };
    };
    const rows = Array.isArray(json.data?.rows) ? json.data.rows : [];
    const row = rows.find((r) => String(r.data?.key ?? "") === token);
    if (!row?.id) throw new Error(`Missing seeded row from table after search jump: ${tableId}`);
    return row.id;
  })();

  await expect(page.locator(`input[aria-label="cell_${tableRowId}_key"]`)).toHaveValue(token, { timeout: 60_000 });
  await expect(page.locator(`input[aria-label="cell_${tableRowId}_value"]`)).toHaveValue(`row ${token}`, {
    timeout: 60_000,
  });

  // memory_entity -> structured memory (entities)
  const resultsEntity = await runSearch();
  const entityCard = resultsEntity.locator(".panel").filter({ hasText: "memory_entity" }).first();
  await expect(entityCard).toBeVisible();
  await entityCard.getByLabel("search_jump", { exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/structured-memory`));
  await expect(page.getByText("character:Alice", { exact: true })).toBeVisible({ timeout: 60_000 });

  // memory_relation -> structured memory character-relations view
  const resultsRel = await runSearch();
  const relCard = resultsRel.locator(".panel").filter({ hasText: "memory_relation" }).first();
  await expect(relCard).toBeVisible();
  await relCard.getByLabel("search_jump", { exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/structured-memory\\?view=character-relations&relationId=${relId}$`));
  await expect(page.getByText("Alice --(friend)→ Bob", { exact: true })).toBeVisible({ timeout: 60_000 });

  // memory_evidence -> structured memory evidence tab
  const resultsEv = await runSearch();
  const evCard = resultsEv.locator(".panel").filter({ hasText: "memory_evidence" }).first();
  await expect(evCard).toBeVisible();
  await evCard.getByLabel("search_jump", { exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/structured-memory`));
  await page.getByRole("button", { name: /structured_tab_evidence/ }).click();
  await page.getByLabel("structured_search", { exact: true }).fill(token);
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  await expect(page.getByText(relationQuote, { exact: true })).toBeVisible({ timeout: 60_000 });
});
