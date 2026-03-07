import fs from "node:fs";
import path from "node:path";
import { performance } from "node:perf_hooks";
import { spawnSync } from "node:child_process";

import { test, expect } from "../lib/ui-test";
import { bootstrapProject } from "../lib/bootstrap";
import { loadState } from "../lib/state";

type MetricSummary = {
  avg_ms: number;
  p50_ms: number;
  p95_ms: number;
  min_ms: number;
  max_ms: number;
};

type ApiMetric = {
  concurrency: number;
  request_latency: MetricSummary;
  batch_latency: MetricSummary;
  avg_requests_per_second: number;
};

type DatasetResult = {
  chapter_count: number;
  project_id: string;
  target_chapter_id: string;
  backend: Record<string, ApiMetric[]>;
  frontend: Record<string, MetricSummary>;
};

const scenario = process.env.AINOVEL_PERF_SCENARIO ?? "full";
const chapterCounts = scenario === "quick" ? [100] : [100, 300, 800];
const apiConcurrencies = scenario === "quick" ? [1, 5] : [1, 5, 20];
const apiRepeats = scenario === "quick" ? 2 : 3;
const uiRepeats = scenario === "quick" ? 2 : 3;
const outputPath = process.env.AINOVEL_PERF_OUTPUT_PATH ?? path.join(process.cwd(), ".artifacts", "perf-results", `wave-d-baseline.${scenario}.json`);

function summarize(values: number[]): MetricSummary {
  const sorted = [...values].sort((left, right) => left - right);
  const pick = (ratio: number) => sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * ratio) - 1))] ?? 0;
  const avg = sorted.reduce((sum, value) => sum + value, 0) / Math.max(sorted.length, 1);
  return {
    avg_ms: round(avg),
    p50_ms: round(pick(0.5)),
    p95_ms: round(pick(0.95)),
    min_ms: round(sorted[0] ?? 0),
    max_ms: round(sorted[sorted.length - 1] ?? 0),
  };
}

function round(value: number): number {
  return Math.round(value * 100) / 100;
}

async function measureRepeated(fn: () => Promise<void>, repeats: number): Promise<MetricSummary> {
  const samples: number[] = [];
  for (let index = 0; index < repeats; index += 1) {
    const started = performance.now();
    await fn();
    samples.push(performance.now() - started);
  }
  return summarize(samples);
}

async function measureApiMetric(
  operation: () => Promise<void>,
  concurrency: number,
): Promise<ApiMetric> {
  const requestLatencies: number[] = [];
  const batchLatencies: number[] = [];

  for (let repeat = 0; repeat < apiRepeats; repeat += 1) {
    const batchStart = performance.now();
    const latencies = await Promise.all(
      Array.from({ length: concurrency }, async () => {
        const started = performance.now();
        await operation();
        return performance.now() - started;
      }),
    );
    const batchElapsed = performance.now() - batchStart;
    requestLatencies.push(...latencies);
    batchLatencies.push(batchElapsed);
  }

  const batchSummary = summarize(batchLatencies);
  return {
    concurrency,
    request_latency: summarize(requestLatencies),
    batch_latency: batchSummary,
    avg_requests_per_second: round((concurrency * 1000) / Math.max(batchSummary.avg_ms, 1)),
  };
}

async function seedProjectDataset(
  request: any,
  chapterCount: number,
): Promise<{ projectId: string; chapterByNumber: Map<number, string> }> {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);
  const chapters = Array.from({ length: chapterCount }, (_, index) => ({
    number: index + 1,
    title: `Perf Chapter ${index + 1}`,
    plan: `Perf plan ${index + 1}`,
  }));

  const bulk = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters/bulk_create`, {
    data: { chapters },
  });
  expect(bulk.ok()).toBeTruthy();
  const bulkJson = (await bulk.json()) as { ok: boolean; data: { chapters: Array<{ id: string; number: number }> } };
  const chapterByNumber = new Map(bulkJson.data.chapters.map((chapter) => [chapter.number, chapter.id]));

  for (const number of [1, Math.max(2, Math.ceil(chapterCount / 2)), chapterCount]) {
    const chapterId = chapterByNumber.get(number);
    if (!chapterId) continue;
    const update = await request.put(`${state.backendUrl}/api/chapters/${chapterId}`, {
      data: {
        content_md: `# Perf Chapter ${number}

Content ${number}`,
        summary: `Summary ${number}`,
        status: number % 2 === 0 ? "drafting" : "done",
      },
    });
    expect(update.ok()).toBeTruthy();
  }

  return { projectId, chapterByNumber };
}


async function fetchAllChapterMeta(request: any, backendUrl: string, projectId: string): Promise<void> {
  let cursor: number | null = null;
  let pageCount = 0;
  while (pageCount < 50) {
    const query = cursor ? `?cursor=${cursor}` : "";
    const response = await request.get(`${backendUrl}/api/projects/${projectId}/chapters/meta${query}`);
    expect(response.ok()).toBeTruthy();
    const body = (await response.json()) as {
      data?: { has_more?: boolean; next_cursor?: number | null };
    };
    if (!body.data?.has_more || !body.data?.next_cursor) {
      return;
    }
    cursor = body.data.next_cursor;
    pageCount += 1;
  }
}

function seedTaskRuntimeFixture(projectId: string, chapterIds: string[]): string {
  const state = loadState();
  const taskId = `perf-task-${projectId}`;
  const python =
    process.platform === "win32"
      ? path.join(state.repoRoot, "backend", ".venv", "Scripts", "python.exe")
      : path.join(state.repoRoot, "backend", ".venv", "bin", "python");
  const script = [
    "import datetime, json, sqlite3, sys",
    "db_path, project_id, task_id, chapters_json = sys.argv[1:5]",
    "chapters = json.loads(chapters_json)",
    "con = sqlite3.connect(db_path)",
    "cur = con.cursor()",
    "now = datetime.datetime.utcnow().isoformat()",
    "cur.execute('INSERT INTO project_tasks (id, project_id, actor_user_id, kind, status, idempotency_key, params_json, result_json, error_json, created_at, started_at, heartbeat_at, finished_at, attempt, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', (task_id, project_id, None, 'batch_generation_orchestrator', 'done', f'perf:{task_id}', json.dumps({'source': 'perf'}), json.dumps({'ok': True}), None, now, now, now, now, 1, now))",
    "event_types = ['running', 'step_started', 'step_succeeded', 'checkpoint']",
    "for idx in range(120):",
    "  chapter_id = chapters[idx % len(chapters)]",
    "  chapter_number = (idx % len(chapters)) + 1",
    "  payload = {",
    "    'source': 'perf_baseline',",
    "    'reason': event_types[idx % len(event_types)],",
    "    'checkpoint': {'status': 'running' if idx < 119 else 'done', 'completed_count': idx, 'failed_count': 0},",
    "    'step': {'chapter_id': chapter_id, 'chapter_number': chapter_number, 'status': 'succeeded', 'attempt_count': 1, 'request_id': f'rid-{idx}', 'generation_run_id': f'run-{idx}' if idx % 5 == 0 else None},",
    "  }",
    "  cur.execute('INSERT INTO project_task_events (project_id, task_id, kind, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)', (project_id, task_id, 'batch_generation_orchestrator', event_types[idx % len(event_types)], json.dumps(payload), now))",
    "con.commit()",
    "con.close()",
  ].join("\n");
  const seeded = spawnSync(python, ["-c", script, state.dbPath, projectId, taskId, JSON.stringify(chapterIds)], {
    encoding: "utf-8",
  });
  expect(seeded.status).toBe(0);
  return taskId;
}

async function measurePreviewOpen(page: any, projectId: string): Promise<void> {
  await page.goto(`/projects/${projectId}/preview`);
  await expect(page.getByText("Perf Chapter 1").first()).toBeVisible();
  await expect(page.locator('[role="listitem"]').first()).toBeVisible();
}

async function measurePreviewNext(page: any, projectId: string): Promise<void> {
  await page.goto(`/projects/${projectId}/preview`);
  await expect(page.getByText("Perf Chapter 1").first()).toBeVisible();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByText("Perf Chapter 2").first()).toBeVisible();
}

async function measureWritingOpen(page: any, projectId: string, chapterId: string, title: string): Promise<void> {
  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);
  await expect(page.locator('input[name="title"]')).toHaveValue(title, { timeout: 60_000 });
}

async function measureTaskCenterOpen(page: any, projectId: string): Promise<void> {
  await page.goto(`/projects/${projectId}/tasks`);
  await expect(page.locator('[aria-label*="taskcenter_refresh"]')).toBeVisible();
}

test("perf: wave-d backend + frontend baseline", async ({ page, request }, testInfo) => {
  test.setTimeout(600_000);
  const state = loadState();
  const datasets: DatasetResult[] = [];

  for (const chapterCount of chapterCounts) {
    const { projectId, chapterByNumber } = await seedProjectDataset(request, chapterCount);
    const middleNumber = Math.max(2, Math.ceil(chapterCount / 2));
    const targetChapterId = chapterByNumber.get(middleNumber) ?? chapterByNumber.get(1);
    const nextChapterId = chapterByNumber.get(Math.min(chapterCount, middleNumber + 1)) ?? chapterByNumber.get(middleNumber);
    expect(targetChapterId).toBeTruthy();
    expect(nextChapterId).toBeTruthy();

    const taskId = seedTaskRuntimeFixture(projectId, [
      chapterByNumber.get(1)!,
      targetChapterId!,
      chapterByNumber.get(chapterCount)!,
    ]);

    const backend = {
      chapter_meta_scan: [] as ApiMetric[],
      chapter_detail: [] as ApiMetric[],
      task_runtime: [] as ApiMetric[],
      memory_retrieve: [] as ApiMetric[],
    };

    for (const concurrency of apiConcurrencies) {
      backend.chapter_meta_scan.push(
        await measureApiMetric(() => fetchAllChapterMeta(request, state.backendUrl, projectId), concurrency),
      );
      backend.chapter_detail.push(
        await measureApiMetric(async () => {
          const response = await request.get(`${state.backendUrl}/api/chapters/${targetChapterId}`);
          expect(response.ok()).toBeTruthy();
        }, concurrency),
      );
      backend.task_runtime.push(
        await measureApiMetric(async () => {
          const response = await request.get(`${state.backendUrl}/api/tasks/${taskId}/runtime`);
          expect(response.ok()).toBeTruthy();
        }, concurrency),
      );
      backend.memory_retrieve.push(
        await measureApiMetric(async () => {
          const response = await request.get(`${state.backendUrl}/api/projects/${projectId}/memory/retrieve`);
          expect(response.ok()).toBeTruthy();
        }, concurrency),
      );
    }

    const frontend = {
      preview_open_ms: await measureRepeated(() => measurePreviewOpen(page, projectId), uiRepeats),
      preview_next_chapter_ms: await measureRepeated(() => measurePreviewNext(page, projectId), uiRepeats),
      writing_open_ms: await measureRepeated(
        () => measureWritingOpen(page, projectId, targetChapterId!, `Perf Chapter ${middleNumber}`),
        uiRepeats,
      ),
      tasks_open_ms: await measureRepeated(() => measureTaskCenterOpen(page, projectId), uiRepeats),
    };

    datasets.push({
      chapter_count: chapterCount,
      project_id: projectId,
      target_chapter_id: targetChapterId!,
      backend,
      frontend,
    });
  }

  const flatBackend = datasets.flatMap((dataset) =>
    Object.entries(dataset.backend).flatMap(([name, metrics]) =>
      metrics.map((metric) => ({ name, chapter_count: dataset.chapter_count, concurrency: metric.concurrency, p95_ms: metric.request_latency.p95_ms })),
    ),
  );
  const slowestBackend = flatBackend.sort((left, right) => right.p95_ms - left.p95_ms)[0] ?? null;

  const flatFrontend = datasets.flatMap((dataset) =>
    Object.entries(dataset.frontend).map(([name, metric]) => ({ name, chapter_count: dataset.chapter_count, p95_ms: metric.p95_ms })),
  );
  const slowestFrontend = flatFrontend.sort((left, right) => right.p95_ms - left.p95_ms)[0] ?? null;

  const payload = {
    scenario,
    generated_at: new Date().toISOString(),
    environment: {
      runner: "playwright-perf",
      db_mode: "isolated-e2e-sqlite",
      backend_url: state.backendUrl,
      frontend_url: state.frontendUrl,
      notes: [
        "frontend timings run in a single browser session; 1/5/20 concurrency applies to backend HTTP endpoints.",
        "results are dev/test baselines on isolated SQLite and should be compared with prod separately.",
      ],
    },
    datasets,
    summary: {
      slowest_backend: slowestBackend,
      slowest_frontend: slowestFrontend,
    },
  };

  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, JSON.stringify(payload, null, 2), "utf-8");
  await testInfo.attach("perf-baseline-json", { path: outputPath, contentType: "application/json" });
});
