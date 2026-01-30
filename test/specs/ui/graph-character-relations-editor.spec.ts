import crypto from "crypto";

import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: character relations editor CRUD + evidence replay", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E Graph Relations Editor", plan: "seed", status: "done" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as { ok: boolean; data: { chapter: { id: string } } };
  const chapterId = createJson.data.chapter.id;

  const aliceId = crypto.randomUUID();
  const bobId = crypto.randomUUID();

  const seedKey = `e2e-graph-editor-seed-${crypto.randomUUID().slice(0, 12)}`;
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

  await page.goto(`/projects/${projectId}/structured-memory?view=character-relations&chapterId=${chapterId}`);

  await page.getByLabel("structured_character_relations_create_from", { exact: true }).selectOption({ value: aliceId });
  await page.getByLabel("structured_character_relations_create_to", { exact: true }).selectOption({ value: bobId });
  await page.getByLabel("structured_character_relations_create_type", { exact: true }).fill("friend");
  await page.getByLabel("structured_character_relations_create_desc", { exact: true }).fill("朋友");
  await page.getByLabel("structured_character_relations_create_submit", { exact: true }).click();

  await expect(page.getByText("Alice --(friend)→ Bob", { exact: true })).toBeVisible({ timeout: 60_000 });

  const listRelations = await request.get(
    `${state.backendUrl}/api/projects/${projectId}/memory/structured?table=relations&limit=200`,
  );
  expect(listRelations.ok()).toBeTruthy();
  const relationsJson = (await listRelations.json()) as {
    ok: boolean;
    data: { relations?: Array<{ id: string; from_entity_id: string; to_entity_id: string; relation_type: string }> };
  };

  const createdRelation = (relationsJson.data.relations ?? []).find(
    (r) => r.from_entity_id === aliceId && r.to_entity_id === bobId && r.relation_type === "friend",
  );
  expect(createdRelation).toBeTruthy();
  const relationId = createdRelation?.id ?? "";

  const quote = `E2E quote:${crypto.randomUUID().slice(0, 8)}`;
  const evidenceId = crypto.randomUUID();
  const evidenceKey = `e2e-graph-editor-ev-${crypto.randomUUID().slice(0, 12)}`;
  const proposeEvidence = await request.post(`${state.backendUrl}/api/chapters/${chapterId}/memory/propose`, {
    data: {
      schema_version: "memory_update_v1",
      idempotency_key: evidenceKey,
      title: "E2E seed evidence",
      ops: [
        {
          op: "upsert",
          target_table: "evidence",
          target_id: evidenceId,
          after: { source_type: "relation", source_id: relationId, quote_md: quote },
        },
      ],
    },
  });
  expect(proposeEvidence.ok()).toBeTruthy();
  const proposeEvidenceJson = (await proposeEvidence.json()) as { ok: boolean; data: { change_set: { id: string } } };
  const evidenceChangeSetId = proposeEvidenceJson.data.change_set.id;

  const applyEvidence = await request.post(`${state.backendUrl}/api/memory_change_sets/${evidenceChangeSetId}/apply`);
  expect(applyEvidence.ok()).toBeTruthy();

  await page.getByLabel(`structured_character_relation_toggle_evidence_${relationId}`, { exact: true }).click();
  await expect(page.getByText(quote, { exact: true })).toBeVisible({ timeout: 60_000 });

  await page.goto(`/projects/${projectId}/graph`);
  await page.getByLabel("graph_query_text", { exact: true }).fill("Alice");
  await page.getByRole("button", { name: /查询/ }).click();

  await expect(page.getByText("Alice --(friend)→ Bob", { exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(quote, { exact: true })).toBeVisible({ timeout: 60_000 });

  await page.goto(`/projects/${projectId}/structured-memory?view=character-relations&chapterId=${chapterId}`);
  await expect(page.getByText("Alice --(friend)→ Bob", { exact: true })).toBeVisible({ timeout: 60_000 });
  await page.getByLabel(`structured_character_relation_edit_${relationId}`, { exact: true }).click();
  await page.getByLabel("structured_character_relations_edit_type", { exact: true }).fill("enemy");
  await page.getByLabel("structured_character_relations_edit_desc", { exact: true }).fill("反目成仇");
  await page.getByLabel("structured_character_relations_edit_submit", { exact: true }).click();
  await expect(page.getByText("Alice --(enemy)→ Bob", { exact: true })).toBeVisible({ timeout: 60_000 });

  await page.getByLabel(`structured_character_relation_delete_${relationId}`, { exact: true }).click();
  await expect(page.getByLabel(`structured_character_relation_${relationId}`, { exact: true })).toHaveCount(0);
});

