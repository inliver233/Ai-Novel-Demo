import crypto from "crypto";

import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: graph query -> character relations create -> rollback", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E Graph Rollback", plan: "seed", status: "done" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as { ok: boolean; data: { chapter: { id: string } } };
  const chapterId = createJson.data.chapter.id;

  const aliceId = crypto.randomUUID();
  const bobId = crypto.randomUUID();

  const seedKey = `e2e-graph-rollback-seed-${crypto.randomUUID().slice(0, 12)}`;
  const proposeSeed = await request.post(`${state.backendUrl}/api/chapters/${chapterId}/memory/propose`, {
    data: {
      schema_version: "memory_update_v1",
      idempotency_key: seedKey,
      title: "E2E seed characters",
      ops: [
        {
          op: "upsert",
          target_table: "entities",
          target_id: aliceId,
          after: { entity_type: "character", name: "Alice" },
        },
        {
          op: "upsert",
          target_table: "entities",
          target_id: bobId,
          after: { entity_type: "character", name: "Bob" },
        },
      ],
    },
  });
  expect(proposeSeed.ok()).toBeTruthy();
  const proposeSeedJson = (await proposeSeed.json()) as { ok: boolean; data: { change_set: { id: string } } };
  const seedChangeSetId = proposeSeedJson.data.change_set.id;

  const applySeed = await request.post(`${state.backendUrl}/api/memory_change_sets/${seedChangeSetId}/apply`);
  expect(applySeed.ok()).toBeTruthy();

  await page.goto(`/projects/${projectId}/graph?chapterId=${encodeURIComponent(chapterId)}`);
  await page.getByLabel("graph_query_text", { exact: true }).fill("Alice");
  await page.getByRole("button", { name: /查询/ }).click();
  await expect(page.getByText("[character] Alice", { exact: true })).toBeVisible({ timeout: 60_000 });

  await page.getByLabel("graph_open_character_relations", { exact: true }).click();
  await expect(page.getByText("人物关系（entity_type=character）", { exact: true })).toBeVisible({ timeout: 60_000 });

  await page.getByLabel("structured_character_relations_create_from", { exact: true }).selectOption({ value: aliceId });
  await page.getByLabel("structured_character_relations_create_to", { exact: true }).selectOption({ value: bobId });
  await page.getByLabel("structured_character_relations_create_type", { exact: true }).fill("friend");
  await page.getByLabel("structured_character_relations_create_desc", { exact: true }).fill("朋友");
  await page.getByLabel("structured_character_relations_create_submit", { exact: true }).click();

  await expect(page.getByText("Alice --(friend)→ Bob", { exact: true })).toBeVisible({ timeout: 60_000 });

  await page.getByLabel("structured_character_relations_rollback_last", { exact: true }).click();
  await expect(page.getByText("Alice --(friend)→ Bob", { exact: true })).toHaveCount(0, { timeout: 60_000 });

  await page.goto(`/projects/${projectId}/graph?chapterId=${encodeURIComponent(chapterId)}`);
  await page.getByLabel("graph_query_text", { exact: true }).fill("Alice");
  await page.getByRole("button", { name: /查询/ }).click();
  await expect(page.getByText("Alice --(friend)→ Bob", { exact: true })).toHaveCount(0, { timeout: 60_000 });
});

