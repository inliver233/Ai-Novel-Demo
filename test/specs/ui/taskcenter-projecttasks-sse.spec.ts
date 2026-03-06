import { test, expect } from "../../lib/ui-test";

import { spawnSync } from "node:child_process";
import path from "node:path";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: task center project tasks update via SSE and survive page reload", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);
  const taskId = `pt-sse-${Date.now()}`;

  const python =
    process.platform === "win32"
      ? path.join(state.repoRoot, "backend", ".venv", "Scripts", "python.exe")
      : path.join(state.repoRoot, "backend", ".venv", "bin", "python");

  await page.goto(`/projects/${projectId}/tasks`);

  const projectTasksPanel = page.locator('[aria-label$="(taskcenter_projecttasks_section)"]');
  await expect(projectTasksPanel).toBeVisible({ timeout: 60_000 });

  const liveStatus = page.getByLabel("taskcenter_projecttask_live_status", { exact: true });
  await expect(liveStatus).toContainText("connected", { timeout: 60_000 });

  await page.getByLabel("taskcenter_projecttask_status", { exact: true }).selectOption("queued");
  await expect(projectTasksPanel).not.toContainText(taskId);

  const script = [
    "import datetime, json, sqlite3, sys",
    "db_path, project_id, task_id = sys.argv[1], sys.argv[2], sys.argv[3]",
    "con = sqlite3.connect(db_path)",
    "cur = con.cursor()",
    "now = datetime.datetime.utcnow().isoformat()",
    "cur.execute(",
    '  "INSERT INTO project_tasks (id, project_id, actor_user_id, kind, status, idempotency_key, params_json, result_json, error_json, created_at, started_at, heartbeat_at, finished_at, attempt, updated_at) "',
    '  "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",',
    "  (task_id, project_id, None, 'noop', 'queued', f'e2e:sse:{task_id}', json.dumps({'e2e': True}), None, None, now, None, None, None, 0, now),",
    ")",
    "payload = json.dumps({",
    "  'reason': 'e2e_sse',",
    "  'task': {",
    "    'id': task_id,",
    "    'project_id': project_id,",
    "    'actor_user_id': None,",
    "    'kind': 'noop',",
    "    'status': 'queued',",
    "    'idempotency_key': f'e2e:sse:{task_id}',",
    "    'attempt': 0,",
    "    'error_type': None,",
    "    'error_message': None,",
    "    'timings': {'created_at': now, 'started_at': None, 'heartbeat_at': None, 'finished_at': None, 'updated_at': now}",
    "  }",
    "}, ensure_ascii=False)",
    "cur.execute(",
    '  "INSERT INTO project_task_events (project_id, task_id, kind, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",',
    "  (project_id, task_id, 'noop', 'queued', payload, now),",
    ")",
    "con.commit()",
    "con.close()",
  ].join("\n");

  const insert = spawnSync(python, ["-c", script, state.dbPath, projectId, taskId], { encoding: "utf-8" });
  expect(insert.status).toBe(0);

  const row = projectTasksPanel.locator("button.surface").filter({ hasText: taskId });
  await expect(row).toBeVisible({ timeout: 60_000 });

  await page.reload();
  await expect(projectTasksPanel).toBeVisible({ timeout: 60_000 });
  await page.getByLabel("taskcenter_projecttask_status", { exact: true }).selectOption("queued");
  await expect(projectTasksPanel.locator("button.surface").filter({ hasText: taskId })).toBeVisible({ timeout: 60_000 });
});
