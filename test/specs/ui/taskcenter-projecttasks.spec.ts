import { test, expect } from "../../lib/ui-test";

import { spawnSync } from "node:child_process";
import path from "node:path";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: task center shows health + can cancel queued project task", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);
  const taskId = `pt-cancel-${Date.now()}`;

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
        "db_path, project_id, task_id = sys.argv[1], sys.argv[2], sys.argv[3]",
        "con = sqlite3.connect(db_path)",
        "cur = con.cursor()",
        "now = datetime.datetime.utcnow().isoformat()",
        "cur.execute(",
        "  \"INSERT INTO project_tasks (id, project_id, actor_user_id, kind, status, idempotency_key, params_json, result_json, error_json, created_at, started_at, finished_at, updated_at) \"",
        "  \"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\",",
        "  (task_id, project_id, None, 'noop', 'queued', f'e2e:cancel:{task_id}', json.dumps({'e2e': True}), None, None, now, None, None, now),",
        ")",
        "con.commit()",
        "con.close()",
      ].join("\n"),
      state.dbPath,
      projectId,
      taskId,
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
});
