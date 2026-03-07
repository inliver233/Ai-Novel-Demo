import { readFile } from "node:fs/promises";

import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test.use({ acceptDownloads: true });

test("ui: download debug bundle (history + context preview)", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const createWorldbookEntry = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries`, {
    data: {
      title: "E2E WB Constant",
      content_md: "dragon",
      enabled: true,
      constant: true,
      keywords: [],
      exclude_recursion: false,
      prevent_recursion: false,
      char_limit: 12000,
      priority: "important",
    },
  });
  expect(createWorldbookEntry.ok()).toBeTruthy();

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as ApiOk<{ chapter: { id: string } }>;
  const chapterId = createJson.data.chapter.id;

  const gen = await request.post(`${state.backendUrl}/api/chapters/${chapterId}/generate`, {
    headers: { "X-LLM-Provider": "openai_compatible" },
    data: {
      mode: "replace",
      instruction: "E2E debug bundle",
      target_word_count: 200,
      plan_first: false,
      post_edit: false,
      memory_injection_enabled: true,
      context: {
        include_world_setting: false,
        include_style_guide: false,
        include_constraints: false,
        include_outline: false,
        include_smart_context: false,
        require_sequential: false,
        character_ids: [],
        previous_chapter: "none",
      },
    },
  });
  expect(gen.ok()).toBeTruthy();
  const genJson = (await gen.json()) as ApiOk<{ generation_run_id: string }>;
  const runId = genJson.data.generation_run_id;
  expect(typeof runId).toBe("string");
  expect(runId.length).toBeGreaterThan(0);

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);

  const openHistory = page.getByLabel("Open generation history (writing_open_generation_history)", { exact: true });
  await expect(openHistory).toBeVisible({ timeout: 60_000 });
  await openHistory.click();
  const history = page.getByRole("dialog", { name: "生成记录", exact: true });
  await expect(history).toBeVisible();

  const firstRun = history.locator("button").filter({ hasText: "ok" }).first();
  await expect(firstRun).toBeVisible({ timeout: 60_000 });
  await firstRun.click();

  await expect(history.getByText("memory_retrieval_log_json", { exact: true })).toBeVisible();
  await expect(history.getByText("semantic_history", { exact: true })).toBeVisible();
  await expect(history.getByText("foreshadow_open_loops", { exact: true })).toBeVisible();

  const [bundleDownload] = await Promise.all([
    page.waitForEvent("download"),
    history.getByRole("button", { name: "下载排障包", exact: true }).click(),
  ]);
  await expect(bundleDownload.failure()).resolves.toBeNull();
  const bundlePath = await bundleDownload.path();
  expect(bundlePath).toBeTruthy();
  const bundleRaw = await readFile(bundlePath!, "utf-8");
  const bundleJson = JSON.parse(bundleRaw) as {
    schema_version: string;
    run?: { id?: string };
    prompt?: { render_log?: unknown };
    memory_retrieval_log?: unknown;
  };
  expect(bundleJson.schema_version).toBe("debug_bundle_v1");
  expect(bundleJson.run?.id).toBe(runId);
  expect(bundleJson.prompt).toBeTruthy();
  expect(bundleJson.prompt).toHaveProperty("render_log");
  expect(bundleJson).toHaveProperty("memory_retrieval_log");
  expect(bundleRaw).not.toContain("test-key");

  await history.getByRole("button", { name: "关闭", exact: true }).click();
  await expect(history).toBeHidden({ timeout: 60_000 });

  await page.getByRole("button", { name: "上下文预览", exact: true }).click();
  const preview = page.getByRole("dialog", { name: "上下文预览", exact: true });
  await expect(preview).toBeVisible();

  const toggle = preview.getByRole("checkbox", { name: "世界书注入", exact: true });
  await expect(toggle).toBeChecked();

  await expect(preview).toContainText("request_id:", { timeout: 60_000 });

  await preview.getByText("触发条目", { exact: true }).click();
  await expect(preview.getByText("E2E WB Constant", { exact: true })).toBeVisible();
  await expect(preview.getByText("constant | priority:important", { exact: true })).toBeVisible();

  const [previewDownload] = await Promise.all([
    page.waitForEvent("download"),
    preview.getByRole("button", { name: "下载预览 bundle", exact: true }).click(),
  ]);
  await expect(previewDownload.failure()).resolves.toBeNull();
  const previewPath = await previewDownload.path();
  expect(previewPath).toBeTruthy();
  const previewRaw = await readFile(previewPath!, "utf-8");
  const previewJson = JSON.parse(previewRaw) as { schema_version: string; project_id: string; request_id?: string | null };
  expect(previewJson.schema_version).toBe("context_preview_bundle_v1");
  expect(previewJson.project_id).toBe(projectId);
});
