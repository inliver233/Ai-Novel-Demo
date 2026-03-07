import { test, expect } from "@playwright/test";

import { spawnSync } from "node:child_process";
import path from "node:path";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("api: project task runtime contract exposes timeline checkpoints artifacts and batch snapshot", async ({
  request,
}) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);
  const taskId = `pt-runtime-${Date.now()}`;
  const batchTaskId = `bt-runtime-${Date.now()}`;
  const runId = `gr-runtime-${Date.now()}`;
  const runtimeProvider = `runtime-contract-provider-${Date.now()}`;
  const item1Id = `${taskId}-item-1`;
  const item2Id = `${taskId}-item-2`;

  const chapter1 = await request.post(
    `${state.backendUrl}/api/projects/${projectId}/chapters`,
    {
      data: { number: 1, title: "第一章", plan: "计划1" },
    },
  );
  expect(chapter1.ok()).toBeTruthy();
  const chapter2 = await request.post(
    `${state.backendUrl}/api/projects/${projectId}/chapters`,
    {
      data: { number: 2, title: "第二章", plan: "计划2" },
    },
  );
  expect(chapter2.ok()).toBeTruthy();

  const python =
    process.platform === "win32"
      ? path.join(state.repoRoot, "backend", ".venv", "Scripts", "python.exe")
      : path.join(state.repoRoot, "backend", ".venv", "bin", "python");

  const script = [
    "import datetime, json, sqlite3, sys",
    "db_path, project_id, task_id, batch_task_id, run_id, runtime_provider = sys.argv[1:7]",
    "con = sqlite3.connect(db_path)",
    "cur = con.cursor()",
    "now = datetime.datetime.utcnow().isoformat()",
    "outline_id = cur.execute('SELECT active_outline_id FROM projects WHERE id = ?', (project_id,)).fetchone()[0]",
    "chapter1_id = cur.execute('SELECT id FROM chapters WHERE project_id = ? AND number = 1', (project_id,)).fetchone()[0]",
    "chapter2_id = cur.execute('SELECT id FROM chapters WHERE project_id = ? AND number = 2', (project_id,)).fetchone()[0]",
    "cur.execute(",
    '  "INSERT INTO generation_runs (id, project_id, actor_user_id, chapter_id, type, provider, model, request_id, prompt_system, prompt_user, prompt_render_log_json, params_json, output_text, error_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",',
    "  (run_id, project_id, None, chapter1_id, 'chapter', 'mock', 'mock-model', 'rid-1', None, None, None, None, 'ok', None, now),",
    ")",
    "cur.execute(",
    '  "INSERT INTO project_tasks (id, project_id, actor_user_id, kind, status, idempotency_key, params_json, result_json, error_json, created_at, started_at, heartbeat_at, finished_at, attempt, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",',
    "  (task_id, project_id, None, 'batch_generation_orchestrator', 'paused', f'batch_generation:{batch_task_id}', json.dumps({'batch_task_id': batch_task_id}), json.dumps({'paused': True}), json.dumps({'code': 'MOCK_FAIL', 'message': 'step failed'}), now, now, now, now, 1, now),",
    ")",
    "cur.execute(",
    '  "INSERT INTO batch_generation_tasks (id, project_id, outline_id, actor_user_id, project_task_id, status, total_count, completed_count, failed_count, skipped_count, cancel_requested, pause_requested, params_json, checkpoint_json, error_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",',
    "  (batch_task_id, project_id, outline_id, None, task_id, 'paused', 2, 1, 1, 0, 0, 1, json.dumps({'runtime_provider': runtime_provider}), json.dumps({'status': 'paused', 'completed_count': 1, 'failed_count': 1}), json.dumps({'code': 'MOCK_FAIL', 'message': 'step failed'}), now, now),",
    ")",
    "items = [",
    `  ('${item1Id}', chapter1_id, 1, 'succeeded', 1, run_id, 'rid-1', None, None),`,
    `  ('${item2Id}', chapter2_id, 2, 'failed', 2, None, 'rid-2', 'mock fail', json.dumps({'code': 'MOCK_FAIL', 'message': 'step failed'})),`,
    "]",
    "for item_id, chapter_id, chapter_number, status, attempt_count, generation_run_id, last_request_id, error_message, last_error_json in items:",
    "  cur.execute(",
    '    "INSERT INTO batch_generation_task_items (id, task_id, chapter_id, chapter_number, status, attempt_count, generation_run_id, last_request_id, error_message, last_error_json, started_at, finished_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",',
    "    (item_id, batch_task_id, chapter_id, chapter_number, status, attempt_count, generation_run_id, last_request_id, error_message, last_error_json, now, now, now, now),",
    "  )",
    "payloads = [",
    "  ('running', {'source': 'batch_generation_worker', 'reason': 'batch_generation_worker_start', 'checkpoint': {'status': 'running', 'completed_count': 0, 'failed_count': 0}}),",
    `  ('step_started', {'source': 'batch_generation_worker', 'reason': 'chapter_started', 'step': {'item_id': '${item1Id}', 'chapter_id': chapter1_id, 'chapter_number': 1, 'status': 'running', 'attempt_count': 1, 'request_id': 'rid-1'}, 'checkpoint': {'status': 'running', 'completed_count': 0, 'failed_count': 0}}),`,
    `  ('step_succeeded', {'source': 'batch_generation_worker', 'reason': 'chapter_succeeded', 'step': {'item_id': '${item1Id}', 'chapter_id': chapter1_id, 'chapter_number': 1, 'status': 'succeeded', 'attempt_count': 1, 'generation_run_id': run_id, 'request_id': 'rid-1'}, 'checkpoint': {'status': 'running', 'completed_count': 1, 'failed_count': 0}}),`,
    `  ('step_failed', {'source': 'batch_generation_worker', 'reason': 'chapter_failed', 'step': {'item_id': '${item2Id}', 'chapter_id': chapter2_id, 'chapter_number': 2, 'status': 'failed', 'attempt_count': 2, 'request_id': 'rid-2', 'error_message': 'mock fail'}, 'checkpoint': {'status': 'paused', 'completed_count': 1, 'failed_count': 1}, 'error': {'code': 'MOCK_FAIL', 'message': 'step failed'}}),`,
    "  ('paused', {'source': 'batch_generation_worker', 'reason': 'chapter_failed', 'checkpoint': {'status': 'paused', 'completed_count': 1, 'failed_count': 1}, 'error': {'code': 'MOCK_FAIL', 'message': 'step failed'}}),",
    "]",
    "for event_type, payload in payloads:",
    "  cur.execute(",
    '    "INSERT INTO project_task_events (project_id, task_id, kind, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",',
    "    (project_id, task_id, 'batch_generation_orchestrator', event_type, json.dumps(payload, ensure_ascii=False), now),",
    "  )",
    "con.commit()",
    "print(json.dumps({'chapter1_id': chapter1_id, 'chapter2_id': chapter2_id}))",
    "con.close()",
  ].join("\n");

  const insert = spawnSync(
    python,
    [
      "-c",
      script,
      state.dbPath,
      projectId,
      taskId,
      batchTaskId,
      runId,
      runtimeProvider,
    ],
    { encoding: "utf-8" },
  );
  expect(insert.status).toBe(0);
  const inserted = JSON.parse(String(insert.stdout || "{}")) as {
    chapter1_id: string;
    chapter2_id: string;
  };

  const runtimeRes = await request.get(
    `${state.backendUrl}/api/tasks/${taskId}/runtime`,
  );
  expect(runtimeRes.ok()).toBeTruthy();
  const runtimeJson = (await runtimeRes.json()) as ApiOk<{
    run: { id: string; status: string };
    timeline: Array<{ event_type: string }>;
    checkpoints: Array<{ checkpoint: { status: string } }>;
    steps: Array<{
      chapter_number: number;
      status: string;
      generation_run_id?: string | null;
    }>;
    artifacts: Array<{ kind: string; id: string; chapter_id?: string | null }>;
    batch: {
      task: { id: string; status: string };
      items: Array<{ chapter_id?: string | null; status: string }>;
    };
  }>;

  const data = runtimeJson.data;
  expect(data.run.id).toBe(taskId);
  expect(data.run.status).toBe("paused");
  expect(data.timeline.map((entry) => entry.event_type)).toEqual([
    "running",
    "step_started",
    "step_succeeded",
    "step_failed",
    "paused",
  ]);
  expect(data.checkpoints.at(-1)?.checkpoint.status).toBe("paused");
  expect(data.steps.map((step) => step.chapter_number)).toEqual([1, 2]);
  expect(data.steps.map((step) => step.status)).toEqual([
    "succeeded",
    "failed",
  ]);
  expect(data.steps[0]?.generation_run_id).toBe(runId);
  expect(data.artifacts).toHaveLength(1);
  expect(data.artifacts[0]).toMatchObject({
    kind: "generation_run",
    id: runId,
    chapter_id: inserted.chapter1_id,
    chapter_number: 1,
    request_id: "rid-1",
  });
  expect(typeof data.artifacts[0]?.event_seq).toBe("number");
  expect((data.artifacts[0]?.event_seq ?? 0) > 0).toBeTruthy();
  expect(data.batch.task.id).toBe(batchTaskId);
  expect(data.batch.task.status).toBe("paused");
  expect(data.batch.items).toHaveLength(2);
  expect(data.batch.items.map((item) => item.status)).toEqual([
    "succeeded",
    "failed",
  ]);
});
