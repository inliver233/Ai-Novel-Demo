import { test, expect } from "@playwright/test";

import { spawnSync } from "node:child_process";
import path from "node:path";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type Frame = { id?: string; event?: string; data?: Record<string, unknown> };

function parseSseFrames(raw: string): Frame[] {
  return raw
    .split("\n\n")
    .map((block) => block.trim())
    .filter((block) => block && !block.startsWith(":"))
    .map((block) => {
      const frame: Frame = {};
      for (const rawLine of block.split("\n")) {
        const line = rawLine.replaceAll("\r", "");
        if (line.startsWith("id: ")) frame.id = line.slice(4).trim();
        else if (line.startsWith("event: ")) frame.event = line.slice(7).trim();
        else if (line.startsWith("data: ")) frame.data = JSON.parse(line.slice(6)) as Record<string, unknown>;
      }
      return frame;
    });
}

test("api: project task events stream supports snapshot and Last-Event-ID replay", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);
  const taskId = `pt-stream-${Date.now()}`;

  const python =
    process.platform === "win32"
      ? path.join(state.repoRoot, "backend", ".venv", "Scripts", "python.exe")
      : path.join(state.repoRoot, "backend", ".venv", "bin", "python");

  const script = [
    "import datetime, json, sqlite3, sys",
    "db_path, project_id, task_id = sys.argv[1], sys.argv[2], sys.argv[3]",
    "con = sqlite3.connect(db_path)",
    "cur = con.cursor()",
    "now = datetime.datetime.utcnow().isoformat()",
    "cur.execute(",
    '  "INSERT INTO project_tasks (id, project_id, actor_user_id, kind, status, idempotency_key, params_json, result_json, error_json, created_at, started_at, heartbeat_at, finished_at, attempt, updated_at) "',
    '  "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",',
    "  (task_id, project_id, None, 'noop', 'succeeded', f'e2e:stream:{task_id}', json.dumps({'e2e': True}), json.dumps({'ok': True}), None, now, now, now, now, 1, now),",
    ")",
    "payloads = [",
    "  ('queued', {'reason': 'seed_queued'}),",
    "  ('running', {'reason': 'seed_running'}),",
    "  ('succeeded', {'reason': 'seed_succeeded'}),",
    "]",
    "seqs = []",
    "for event_type, extra in payloads:",
    "  payload = json.dumps({",
    "    **extra,",
    "    'task': {",
    "      'id': task_id,",
    "      'project_id': project_id,",
    "      'actor_user_id': None,",
    "      'kind': 'noop',",
    "      'status': 'succeeded' if event_type == 'succeeded' else ('running' if event_type == 'running' else 'queued'),",
    "      'idempotency_key': f'e2e:stream:{task_id}',",
    "      'attempt': 1,",
    "      'error_type': None,",
    "      'error_message': None,",
    "      'timings': {'created_at': now, 'started_at': now, 'heartbeat_at': now, 'finished_at': now, 'updated_at': now}",
    "    }",
    "  }, ensure_ascii=False)",
    "  cur.execute(",
    '    "INSERT INTO project_task_events (project_id, task_id, kind, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",',
    "    (project_id, task_id, 'noop', event_type, payload, now),",
    "  )",
    "  seqs.append(cur.lastrowid)",
    "con.commit()",
    "print(json.dumps({'seqs': seqs}))",
    "con.close()",
  ].join("\n");

  const insert = spawnSync(python, ["-c", script, state.dbPath, projectId, taskId], { encoding: "utf-8" });
  expect(insert.status).toBe(0);
  const inserted = JSON.parse(String(insert.stdout || "{}")) as { seqs: number[] };
  const seqs = inserted.seqs || [];
  expect(seqs.length).toBe(3);

  const snapshotRes = await request.get(`${state.backendUrl}/api/projects/${projectId}/task-events/stream?stream_timeout_seconds=0.2`);
  expect(snapshotRes.ok()).toBeTruthy();
  const snapshotFrames = parseSseFrames(await snapshotRes.text());
  expect(snapshotFrames[0]?.event).toBe("snapshot");
  expect(snapshotFrames[0]?.id).toBe(String(seqs[2]));
  expect(snapshotFrames[0]?.data?.cursor).toBe(seqs[2]);

  const replayRes = await request.get(`${state.backendUrl}/api/projects/${projectId}/task-events/stream?stream_timeout_seconds=0.2`, {
    headers: { "Last-Event-ID": String(seqs[0]) },
  });
  expect(replayRes.ok()).toBeTruthy();
  const replayFrames = parseSseFrames(await replayRes.text());
  expect(replayFrames.map((frame) => frame.event)).toEqual(["project_task", "project_task"]);
  expect(replayFrames.map((frame) => frame.id)).toEqual([String(seqs[1]), String(seqs[2])]);
  expect(replayFrames.map((frame) => frame.data?.event_type)).toEqual(["running", "succeeded"]);
});
