import { test, expect } from "../../lib/ui-test";

import { spawnSync } from "node:child_process";
import path from "node:path";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: batch runtime stays consistent between Writing and TaskCenter after recovery", async ({
  page,
  request,
}) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);
  const projectTaskId = `pt-batch-sync-${Date.now()}`;
  const batchTaskId = `bt-batch-sync-${Date.now()}`;
  const runId = `gr-batch-sync-${Date.now()}`;
  const runtimeProvider = `batch-sync-provider-${Date.now()}`;
  const item1Id = `${projectTaskId}-item-1`;
  const item2Id = `${projectTaskId}-item-2`;

  const chapter1 = await request.post(
    `${state.backendUrl}/api/projects/${projectId}/chapters`,
    {
      data: { number: 1, title: "Chapter 1", plan: "Plan 1" },
    },
  );
  expect(chapter1.ok()).toBeTruthy();
  const chapter1Json = (await chapter1.json()) as {
    ok: true;
    data: { chapter: { id: string } };
  };
  const chapter1Id = chapter1Json.data.chapter.id;

  const chapter2 = await request.post(
    `${state.backendUrl}/api/projects/${projectId}/chapters`,
    {
      data: { number: 2, title: "Chapter 2", plan: "Plan 2" },
    },
  );
  expect(chapter2.ok()).toBeTruthy();
  const chapter2Json = (await chapter2.json()) as {
    ok: true;
    data: { chapter: { id: string } };
  };
  const chapter2Id = chapter2Json.data.chapter.id;

  const python =
    process.platform === "win32"
      ? path.join(state.repoRoot, "backend", ".venv", "Scripts", "python.exe")
      : path.join(state.repoRoot, "backend", ".venv", "bin", "python");

  const script = [
    "import datetime, json, sqlite3, sys",
    "db_path, project_id, chapter1_id, chapter2_id, project_task_id, batch_task_id, run_id, item1_id, item2_id, runtime_provider = sys.argv[1:11]",
    "con = sqlite3.connect(db_path)",
    "cur = con.cursor()",
    "now = datetime.datetime.utcnow().isoformat()",
    "outline_id = cur.execute('SELECT active_outline_id FROM projects WHERE id = ?', (project_id,)).fetchone()[0]",
    "cur.execute(",
    '  "INSERT INTO generation_runs (id, project_id, actor_user_id, chapter_id, type, provider, model, request_id, prompt_system, prompt_user, prompt_render_log_json, params_json, output_text, error_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",',
    "  (run_id, project_id, None, chapter1_id, 'chapter', 'mock', 'mock-model', 'rid-sync-1', None, None, None, None, 'ok', None, now),",
    ")",
    "cur.execute(",
    '  "INSERT INTO project_tasks (id, project_id, actor_user_id, kind, status, idempotency_key, params_json, result_json, error_json, created_at, started_at, heartbeat_at, finished_at, attempt, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",',
    "  (project_task_id, project_id, None, 'batch_generation_orchestrator', 'paused', f'batch_generation:{batch_task_id}', json.dumps({'batch_task_id': batch_task_id}), json.dumps({'paused': True}), json.dumps({'code': 'MOCK_FAIL', 'message': 'step failed'}), now, now, now, now, 1, now),",
    ")",
    "cur.execute(",
    '  "INSERT INTO batch_generation_tasks (id, project_id, outline_id, actor_user_id, project_task_id, status, total_count, completed_count, failed_count, skipped_count, cancel_requested, pause_requested, params_json, checkpoint_json, error_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",',
    "  (batch_task_id, project_id, outline_id, None, project_task_id, 'paused', 2, 1, 1, 0, 0, 0, json.dumps({'runtime_provider': runtime_provider}), json.dumps({'status': 'paused', 'completed_count': 1, 'failed_count': 1, 'skipped_count': 0}), json.dumps({'code': 'MOCK_FAIL', 'message': 'step failed'}), now, now),",
    ")",
    "items = [",
    "  (item1_id, chapter1_id, 1, 'succeeded', 1, run_id, 'rid-sync-1', None, None),",
    "  (item2_id, chapter2_id, 2, 'failed', 2, None, 'rid-sync-2', 'mock fail', json.dumps({'code': 'MOCK_FAIL', 'message': 'step failed'})),",
    "]",
    "for item_id, chapter_id, chapter_number, status, attempt_count, generation_run_id, last_request_id, error_message, last_error_json in items:",
    "  cur.execute(",
    '    "INSERT INTO batch_generation_task_items (id, task_id, chapter_id, chapter_number, status, attempt_count, generation_run_id, last_request_id, error_message, last_error_json, started_at, finished_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",',
    "    (item_id, batch_task_id, chapter_id, chapter_number, status, attempt_count, generation_run_id, last_request_id, error_message, last_error_json, now, now, now, now),",
    "  )",
    "payloads = [",
    "  ('running', {'source': 'batch_generation_worker', 'reason': 'batch_generation_worker_start', 'checkpoint': {'status': 'running', 'completed_count': 0, 'failed_count': 0, 'skipped_count': 0}}),",
    "  ('step_succeeded', {'source': 'batch_generation_worker', 'reason': 'chapter_succeeded', 'step': {'item_id': item1_id, 'chapter_id': chapter1_id, 'chapter_number': 1, 'status': 'succeeded', 'attempt_count': 1, 'generation_run_id': run_id, 'request_id': 'rid-sync-1'}, 'checkpoint': {'status': 'running', 'completed_count': 1, 'failed_count': 0, 'skipped_count': 0}}),",
    "  ('step_failed', {'source': 'batch_generation_worker', 'reason': 'chapter_failed', 'step': {'item_id': item2_id, 'chapter_id': chapter2_id, 'chapter_number': 2, 'status': 'failed', 'attempt_count': 2, 'request_id': 'rid-sync-2', 'error_message': 'mock fail'}, 'checkpoint': {'status': 'paused', 'completed_count': 1, 'failed_count': 1, 'skipped_count': 0}, 'error': {'code': 'MOCK_FAIL', 'message': 'step failed'}}),",
    "  ('paused', {'source': 'batch_generation_worker', 'reason': 'chapter_failed', 'checkpoint': {'status': 'paused', 'completed_count': 1, 'failed_count': 1, 'skipped_count': 0}, 'error': {'code': 'MOCK_FAIL', 'message': 'step failed'}}),",
    "]",
    "for event_type, payload in payloads:",
    "  cur.execute(",
    '    "INSERT INTO project_task_events (project_id, task_id, kind, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",',
    "    (project_id, project_task_id, 'batch_generation_orchestrator', event_type, json.dumps(payload, ensure_ascii=False), now),",
    "  )",
    "con.commit()",
    "con.close()",
  ].join("\n");

  const insert = spawnSync(
    python,
    [
      "-c",
      script,
      state.dbPath,
      projectId,
      chapter1Id,
      chapter2Id,
      projectTaskId,
      batchTaskId,
      runId,
      item1Id,
      item2Id,
      runtimeProvider,
    ],
    { encoding: "utf-8" },
  );
  expect(insert.status).toBe(0);

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapter1Id}`);
  await page
    .getByLabel("Open batch generation (writing_open_batch_generation)", {
      exact: true,
    })
    .click();

  const summary = page.getByLabel("batch_generation_runtime_summary", {
    exact: true,
  });
  await expect(summary).toContainText("paused", { timeout: 60_000 });
  await expect(
    page.getByLabel("batch_generation_items", { exact: true }),
  ).toContainText("failed", { timeout: 60_000 });

  await page
    .getByLabel("Skip failed chapters (batch_generation_skip_failed)", {
      exact: true,
    })
    .click();

  await expect(summary).toContainText("succeeded", { timeout: 60_000 });
  await expect(
    page.getByLabel("batch_generation_items", { exact: true }),
  ).toContainText("skipped", { timeout: 60_000 });

  await page
    .getByLabel("Open TaskCenter (batch_generation_open_task_center)", {
      exact: true,
    })
    .click();

  const projectTasksPanel = page.locator(
    '[aria-label$="(taskcenter_projecttasks_section)"]',
  );
  await expect(projectTasksPanel).toBeVisible({ timeout: 60_000 });
  const row = projectTasksPanel
    .locator("button.surface")
    .filter({ hasText: projectTaskId });
  await expect(row).toBeVisible({ timeout: 60_000 });
  await row.first().click();

  const batchSection = page.getByLabel("projecttask_runtime_batch", {
    exact: true,
  });
  await expect(batchSection).toContainText("succeeded", { timeout: 60_000 });
  await expect(
    page.getByLabel("projecttask_runtime_batch_items", { exact: true }),
  ).toContainText("skipped", { timeout: 60_000 });
  await expect(
    page.getByLabel("projecttask_runtime_timeline", { exact: true }),
  ).toContainText("step_skipped", { timeout: 60_000 });

  await page.reload();
  await expect(
    page.locator('[aria-label$="(taskcenter_projecttasks_section)"]'),
  ).toBeVisible({ timeout: 60_000 });
  const rowAfterReload = page
    .locator('[aria-label$="(taskcenter_projecttasks_section)"]')
    .locator("button.surface")
    .filter({ hasText: projectTaskId });
  await expect(rowAfterReload).toBeVisible({ timeout: 60_000 });
  await rowAfterReload.first().click();
  await expect(
    page.getByLabel("projecttask_runtime_batch", { exact: true }),
  ).toContainText("succeeded", { timeout: 60_000 });
  await expect(
    page.getByLabel("projecttask_runtime_batch_items", { exact: true }),
  ).toContainText("skipped", { timeout: 60_000 });
});
