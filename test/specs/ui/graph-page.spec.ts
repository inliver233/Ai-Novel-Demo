import crypto from "crypto";

import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: GraphPage loads graph query result", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "用于 GraphPage", status: "done" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as { ok: boolean; data: { chapter: { id: string } } };
  const chapterId = createJson.data.chapter.id;

  const aliceId = crypto.randomUUID();
  const bobId = crypto.randomUUID();
  const relId = crypto.randomUUID();

  const idempotencyKey = `e2e-graph-${crypto.randomUUID().slice(0, 12)}`;
  const propose = await request.post(`${state.backendUrl}/api/chapters/${chapterId}/memory/propose`, {
    data: {
      schema_version: "memory_update_v1",
      idempotency_key: idempotencyKey,
      title: "E2E graph seed",
      ops: [
        {
          op: "upsert",
          target_table: "entities",
          target_id: aliceId,
          after: { entity_type: "character", name: "Alice", attributes: { aliases: ["Alicia"] } },
        },
        {
          op: "upsert",
          target_table: "entities",
          target_id: bobId,
          after: { entity_type: "character", name: "Bob" },
        },
        {
          op: "upsert",
          target_table: "relations",
          target_id: relId,
          after: { from_entity_id: aliceId, to_entity_id: bobId, relation_type: "knows", description_md: "朋友" },
        },
      ],
    },
  });
  expect(propose.ok()).toBeTruthy();
  const proposeJson = (await propose.json()) as { ok: boolean; data: { change_set: { id: string } } };
  const changeSetId = proposeJson.data.change_set.id;

  const apply = await request.post(`${state.backendUrl}/api/memory_change_sets/${changeSetId}/apply`);
  expect(apply.ok()).toBeTruthy();

  await page.goto(`/projects/${projectId}/graph`);

  await page.getByLabel("graph_query_text", { exact: true }).fill("Alice");
  await page.getByRole("button", { name: /查询/ }).click();

  await expect(page.getByText("[character] Alice", { exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("Alice --(knows)→ Bob", { exact: true })).toBeVisible({ timeout: 60_000 });
});
