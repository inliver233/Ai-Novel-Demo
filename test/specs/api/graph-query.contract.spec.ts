import crypto from "crypto";

import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("api: graph/query returns stable shape + query_preprocessing + evidence", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const settings = await request.put(`${state.backendUrl}/api/projects/${projectId}/settings`, {
    data: {
      query_preprocessing: {
        enabled: true,
        tags: ["tag"],
        exclusion_rules: ["EXCLUDE_ME"],
        index_ref_enhance: true,
      },
    },
  });
  expect(settings.ok()).toBeTruthy();

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E Graph Contract", plan: "seed", status: "done" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as ApiOk<{ chapter: { id: string } }>;
  const chapterId = createJson.data.chapter.id;

  const aliceId = crypto.randomUUID();
  const bobId = crypto.randomUUID();
  const relId = crypto.randomUUID();
  const evId = crypto.randomUUID();

  const idempotencyKey = `e2e-graph-contract-${crypto.randomUUID().slice(0, 12)}`;
  const propose = await request.post(`${state.backendUrl}/api/chapters/${chapterId}/memory/propose`, {
    data: {
      schema_version: "memory_update_v1",
      idempotency_key: idempotencyKey,
      title: "E2E graph contract seed",
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
        {
          op: "upsert",
          target_table: "evidence",
          target_id: evId,
          after: {
            source_type: "entity",
            source_id: aliceId,
            quote_md: "Alice 在第一章提到 Bob。",
            attributes: { chapter_id: chapterId },
          },
        },
      ],
    },
  });
  expect(propose.ok()).toBeTruthy();
  const proposeJson = (await propose.json()) as ApiOk<{ change_set: { id: string } }>;
  const changeSetId = proposeJson.data.change_set.id;

  const apply = await request.post(`${state.backendUrl}/api/memory_change_sets/${changeSetId}/apply`);
  expect(apply.ok()).toBeTruthy();

  const queryText = "#tag Alice EXCLUDE_ME 第12章";
  const query = await request.post(`${state.backendUrl}/api/projects/${projectId}/graph/query`, {
    data: { query_text: queryText, max_nodes: 10, max_edges: 50 },
  });
  expect(query.ok()).toBeTruthy();
  const queryJson = (await query.json()) as ApiOk<{
    result: Record<string, unknown>;
    raw_query_text: string;
    normalized_query_text: string;
    preprocess_obs: Record<string, unknown>;
  }>;
  expect(queryJson.ok).toBe(true);
  expect(queryJson.data.raw_query_text).toBe(queryText);
  expect(typeof queryJson.data.normalized_query_text).toBe("string");
  expect(queryJson.data.normalized_query_text).toContain("Alice");
  expect(queryJson.data.normalized_query_text).toContain("chapter:12");
  expect(queryJson.data.normalized_query_text).not.toContain("#tag");

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const obs = queryJson.data.preprocess_obs as any;
  expect(obs.enabled).toBe(true);
  expect((obs.extracted_tags ?? [])).toContain("tag");
  expect((obs.applied_exclusion_rules ?? [])).toContain("EXCLUDE_ME");
  expect((obs.index_refs ?? [])).toContain("chapter:12");

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const result = queryJson.data.result as any;
  expect(typeof result.enabled).toBe("boolean");
  expect(result.disabled_reason === null || typeof result.disabled_reason === "string").toBeTruthy();
  expect(result.error === undefined || result.error === null || typeof result.error === "string").toBeTruthy();
  expect(typeof result.query_text).toBe("string");
  expect(result.query_text).toBe(queryJson.data.normalized_query_text);
  expect(typeof result.params).toBe("object");
  expect(typeof result.matched).toBe("object");
  expect(Array.isArray(result.nodes)).toBe(true);
  expect(Array.isArray(result.edges)).toBe(true);
  expect(Array.isArray(result.evidence)).toBe(true);
  expect(typeof result.prompt_block?.identifier).toBe("string");
  expect(typeof result.prompt_block?.role).toBe("string");
  expect(typeof result.prompt_block?.text_md).toBe("string");
  expect(typeof result.truncated?.nodes).toBe("boolean");
  expect(typeof result.truncated?.edges).toBe("boolean");
  expect(typeof result.timings_ms).toBe("object");

  // Evidence structure should be stable.
  expect(result.evidence.length).toBeGreaterThan(0);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const ev = result.evidence[0] as any;
  expect(typeof ev.id).toBe("string");
  expect(typeof ev.source_type).toBe("string");
  expect(typeof ev.source_id).toBe("string");
  expect(typeof ev.quote_md).toBe("string");
  expect(typeof ev.attributes).toBe("object");
  expect(typeof ev.created_at).toBe("string");
  expect(String(ev.created_at)).toMatch(/^\d{4}-\d{2}-\d{2}T/);

  // Must not leak known secret patterns.
  const raw = JSON.stringify(queryJson);
  expect(raw).not.toMatch(/sk-[a-zA-Z0-9]{10,}/);
});
