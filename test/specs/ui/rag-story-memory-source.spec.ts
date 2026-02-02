import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("ui: vector rebuild defaults include story_memory source", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const settingsRes = await request.put(`${state.backendUrl}/api/projects/${projectId}/settings`, {
    data: {
      vector_embedding_base_url: state.mockLlmBaseUrl,
      vector_embedding_model: "text-embedding-mock",
      vector_embedding_api_key: "test-key",
    },
  });
  expect(settingsRes.ok()).toBeTruthy();

  const marker = `E2E_STORY_MEMORY_CHAPTER_SUMMARY_${Date.now()}`;
  const createRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/story_memories`, {
    data: {
      memory_type: "chapter_summary",
      title: "E2E story_memory chapter_summary",
      content: marker,
      importance_score: 0.6,
      tags: ["e2e", "summary"],
      story_timeline: 0,
      text_position: -1,
      text_length: 0,
      is_foreshadow: false,
    },
  });
  expect(createRes.ok()).toBeTruthy();

  const rebuildRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/vector/rebuild`, { data: {} });
  expect(rebuildRes.ok()).toBeTruthy();
  const rebuildJson = (await rebuildRes.json()) as ApiOk<{ result: { enabled?: boolean; skipped?: boolean; disabled_reason?: string; error?: string } }>;
  const rebuildResult = rebuildJson.data?.result ?? {};
  if (rebuildResult.enabled === false || rebuildResult.skipped) {
    throw new Error(
      `vector/rebuild did not run: enabled=${String(rebuildResult.enabled)} skipped=${String(rebuildResult.skipped)} ` +
        `disabled_reason=${String(rebuildResult.disabled_reason ?? "-")} error=${String(rebuildResult.error ?? "-")}`,
    );
  }

  await page.goto(`/projects/${projectId}/rag`);
  await expect(page.getByText("Vector RAG 管理", { exact: true })).toBeVisible();

  const storyInput = page
    .getByText("故事记忆（story_memory）", { exact: true })
    .locator("..")
    .locator("input[type=\"checkbox\"]");
  await expect(storyInput).toBeChecked();

  for (const labelText of ["世界书（worldbook）", "大纲（outline）", "章节（chapter）"] as const) {
    const input = page.getByText(labelText, { exact: true }).locator("..").locator("input[type=\"checkbox\"]");
    if (await input.isChecked()) await page.getByText(labelText, { exact: true }).click();
    await expect(input).not.toBeChecked();
  }

  await page.getByLabel("query_text", { exact: true }).fill(marker);
  await page.getByLabel("查询 (rag_query)", { exact: true }).click();

  const rawDetails = page.locator("summary", { hasText: "raw vector query result" }).locator("..");
  await expect(rawDetails).toBeVisible();
  await rawDetails.locator("summary").click();
  await expect(rawDetails).toHaveAttribute("open", "");

  const queryResultText = (await rawDetails.locator("pre").innerText()).trim();
  const queryResult = JSON.parse(queryResultText) as { enabled?: boolean; disabled_reason?: string | null; error?: string | null; candidates?: unknown };
  if (!queryResult.enabled) {
    throw new Error(
      `vector/query failed: disabled_reason=${String(queryResult.disabled_reason ?? "-")} error=${String(queryResult.error ?? "-")}`,
    );
  }

  const candidates = Array.isArray(queryResult.candidates) ? queryResult.candidates : [];
  const hasStoryMemory = candidates.some((c) => {
    if (!c || typeof c !== "object") return false;
    const meta = (c as { metadata?: unknown }).metadata;
    if (!meta || typeof meta !== "object") return false;
    return (meta as { source?: unknown }).source === "story_memory";
  });

  expect(hasStoryMemory).toBe(true);
});

