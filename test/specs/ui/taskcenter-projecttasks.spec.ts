import { test, expect } from "../../lib/ui-test";

import { spawnSync } from "node:child_process";
import path from "node:path";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: task center shows health + can cancel queued project task", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);
  const taskId = `pt-cancel-${Date.now()}`;
  const failedTaskId = `pt-failed-${Date.now()}`;
  const runId = `run-e2e-${Date.now()}`;

  // Insert a deterministic queued ProjectTask into the E2E SQLite DB.
  // This avoids flakiness from inline worker timing (tasks may finish too fast to stay queued).
  const python =
    process.platform === "win32"
      ? path.join(state.repoRoot, "backend", ".venv", "Scripts", "python.exe")
      : path.join(state.repoRoot, "backend", ".venv", "bin", "python");
  const insert = spawnSync(
    python,
    [
      "-c",
      [
        "import datetime, json, sqlite3, sys",
        "db_path, project_id, task_id, failed_task_id, run_id = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]",
        "con = sqlite3.connect(db_path)",
        "cur = con.cursor()",
        "now = datetime.datetime.utcnow().isoformat()",
        "cur.execute(",
        "  \"INSERT INTO project_tasks (id, project_id, actor_user_id, kind, status, idempotency_key, params_json, result_json, error_json, created_at, started_at, finished_at, updated_at) \"",
        "  \"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\",",
        "  (task_id, project_id, None, 'noop', 'queued', f'e2e:cancel:{task_id}', json.dumps({'e2e': True}), None, None, now, None, None, now),",
        ")",
        "cur.execute(",
        "  \"INSERT INTO generation_runs (id, project_id, actor_user_id, chapter_id, type, provider, model, request_id, prompt_system, prompt_user, prompt_render_log_json, params_json, output_text, error_json, created_at) \"",
        "  \"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\",",
        "  (run_id, project_id, None, None, 'table_ai_update_auto_propose', None, None, 'e2e', '', '', None, '{}', None, '{\"code\":\"LLM_TIMEOUT\",\"details\":{\"status_code\":504}}', now),",
        ")",
        "cur.execute(",
        "  \"INSERT INTO project_tasks (id, project_id, actor_user_id, kind, status, idempotency_key, params_json, result_json, error_json, created_at, started_at, finished_at, updated_at) \"",
        "  \"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\",",
        "  (",
        "    failed_task_id,",
        "    project_id,",
        "    None,",
        "    'table_ai_update',",
        "    'failed',",
        "    f'e2e:failed:{failed_task_id}',",
        "    json.dumps({'e2e': True}),",
        "    None,",
        "    json.dumps({",
        "      'error_type': 'AppError',",
        "      'code': 'TABLE_AI_UPDATE_FAILED',",
        "      'message': 'table_ai_update failed',",
        "      'details': {'reason': 'llm_call_failed', 'run_id': run_id, 'how_to_fix': ['e2e']}",
        "    }),",
        "    now,",
        "    now,",
        "    now,",
        "    now",
        "  ),",
        ")",
        "con.commit()",
        "con.close()",
      ].join("\n"),
      state.dbPath,
      projectId,
      taskId,
      failedTaskId,
      runId,
    ],
    { encoding: "utf-8" },
  );
  expect(insert.status).toBe(0);

  await page.goto(`/projects/${projectId}/tasks`);

  const banner = page.getByRole("region", { name: "队列状态 (taskcenter_queue_status)", exact: true });
  await expect(banner).toBeVisible({ timeout: 60_000 });
  await expect(banner).toContainText("queue_backend");
  await expect(banner).toContainText("effective_backend");
  await expect(banner).toContainText("inline");
  await expect(banner.getByRole("button", { name: "复制 health 请求 ID（request_id）", exact: true })).toBeVisible();

  const projectTasksPanel = page.getByRole("region", { name: "项目任务 (taskcenter_projecttasks_section)", exact: true });
  await expect(projectTasksPanel).toBeVisible();

  await page.getByLabel("taskcenter_projecttask_status", { exact: true }).selectOption("queued");

  const rows = projectTasksPanel.locator("button.surface");
  const row = rows.filter({ hasText: taskId });
  await expect(row).toBeVisible({ timeout: 60_000 });
  await row.first().click();

  const detail = page.getByRole("dialog", { name: "ProjectTask 详情", exact: true });
  await expect(detail).toBeVisible();

  page.once("dialog", (dialog) => dialog.accept());
  await detail
    .getByRole("button", { name: "取消项目任务 (taskcenter_projecttask_cancel_detail)", exact: true })
    .click();

  const overview = detail.getByRole("region", { name: "projecttask_overview", exact: true });
  await expect(overview).toContainText("canceled", { timeout: 60_000 });

  await detail.getByRole("button", { name: "关闭", exact: true }).click();

  await page.getByLabel("taskcenter_projecttask_status", { exact: true }).selectOption("failed");
  const failedRow = projectTasksPanel.locator("button.surface").filter({ hasText: failedTaskId });
  await expect(failedRow).toBeVisible({ timeout: 60_000 });
  await failedRow.first().click();

  const detail2 = page.getByRole("dialog", { name: "ProjectTask 详情", exact: true });
  await expect(detail2).toBeVisible();

  const runSection = detail2.getByRole("region", { name: "projecttask_generation_run", exact: true });
  await expect(runSection).toContainText(runId);
  await expect(detail2.getByRole("button", { name: "复制 run_id (taskcenter_projecttask_copy_run_id)", exact: true })).toBeVisible();
  await expect(detail2.getByRole("link", { name: "打开运行记录 (taskcenter_projecttask_open_generation_run)", exact: true })).toBeVisible();
});
