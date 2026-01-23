import { test, expect } from "../../lib/ui-test";

import type { APIRequestContext, Page } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

async function setupProjectAndChapter(request: APIRequestContext): Promise<{
  projectId: string;
  chapterId: string;
}> {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "要点 A；要点 B" },
  });
  if (!create.ok()) throw new Error(`Failed to create chapter: ${create.status()} ${await create.text()}`);
  const createJson = (await create.json()) as { ok: boolean; data: { chapter: { id: string } } };
  return { projectId, chapterId: createJson.data.chapter.id };
}

async function openAiDrawer(page: Page) {
  await page.getByRole("button", { name: "AI 生成", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "AI 生成", exact: true });
  await expect(drawer).toBeVisible();
  await drawer.getByRole("button", { name: "高级参数", exact: true }).click();
  return drawer;
}

test("ui: writing dirty -> save and generate", async ({ page, request }) => {
  const { projectId, chapterId } = await setupProjectAndChapter(request);

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);
  await expect(page.getByRole("textbox", { name: "标题", exact: true })).toHaveValue("E2E 第一章", { timeout: 60_000 });
  const content = page.locator('textarea[name="content_md"]');
  await expect(content).toBeVisible();

  const drawer = await openAiDrawer(page);
  await drawer.getByRole("checkbox", { name: "流式生成（beta）" }).uncheck();

  const dirtyMarker = "E2E_DIRTY_SAVE_AND_GENERATE";
  await content.fill(dirtyMarker);
  await expect(drawer.getByRole("button", { name: "保存", exact: true })).toBeEnabled();

  // Make generation deterministic and fast (this spec focuses on "unsaved confirm" behavior).
  await page.route(`**/api/chapters/${chapterId}/generate`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        data: { content_md: "E2E_GENERATED_OUTPUT", summary: "E2E summary", raw_output: "" },
        request_id: "e2e-request",
      }),
    });
  });

  const saveReqP = page.waitForRequest(
    (req) => req.method() === "PUT" && req.url().endsWith(`/api/chapters/${chapterId}`),
  );
  const genReqP = page.waitForRequest(
    (req) => req.method() === "POST" && req.url().endsWith(`/api/chapters/${chapterId}/generate`),
  );

  await drawer.getByRole("button", { name: "生成", exact: true }).click();
  const confirm = page.getByRole("dialog", { name: "章节有未保存修改，如何生成？", exact: true });
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", { name: "保存并生成", exact: true }).click();

  const first = await Promise.race([saveReqP.then(() => "save"), genReqP.then(() => "generate")]);
  expect(first).toBe("save");

  const saveReq = await saveReqP;
  const saveBody = saveReq.postDataJSON() as { content_md?: string };
  expect(saveBody.content_md).toBe(dirtyMarker);

  await genReqP;

  await expect(content).toHaveValue(/E2E_GENERATED_OUTPUT/);
  await expect(content).not.toHaveValue(new RegExp(dirtyMarker));
});

test("ui: writing dirty -> generate without saving", async ({ page, request }) => {
  const { projectId, chapterId } = await setupProjectAndChapter(request);

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);
  await expect(page.getByRole("textbox", { name: "标题", exact: true })).toHaveValue("E2E 第一章", { timeout: 60_000 });
  const content = page.locator('textarea[name="content_md"]');
  await expect(content).toBeVisible();

  const drawer = await openAiDrawer(page);
  await drawer.getByRole("checkbox", { name: "流式生成（beta）" }).uncheck();

  const dirtyMarker = "E2E_DIRTY_GENERATE_NO_SAVE";
  await content.fill(dirtyMarker);
  await expect(drawer.getByRole("button", { name: "保存", exact: true })).toBeEnabled();

  await page.route(`**/api/chapters/${chapterId}/generate`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        data: { content_md: "E2E_GENERATED_NO_SAVE", summary: "E2E summary", raw_output: "" },
        request_id: "e2e-request",
      }),
    });
  });

  const events: Array<"save" | "generate"> = [];
  page.on("request", (req) => {
    if (req.method() === "PUT" && req.url().endsWith(`/api/chapters/${chapterId}`)) events.push("save");
    if (req.method() === "POST" && req.url().endsWith(`/api/chapters/${chapterId}/generate`)) events.push("generate");
  });
  const genReqP = page.waitForRequest(
    (req) => req.method() === "POST" && req.url().endsWith(`/api/chapters/${chapterId}/generate`),
  );

  await drawer.getByRole("button", { name: "生成", exact: true }).click();
  const confirm = page.getByRole("dialog", { name: "章节有未保存修改，如何生成？", exact: true });
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", { name: /直接生成/ }).click();

  await genReqP;
  expect(events[0]).toBe("generate");

  await expect(content).toHaveValue(/E2E_GENERATED_NO_SAVE/);
  await expect(content).not.toHaveValue(new RegExp(dirtyMarker));
});

test("ui: writing dirty -> cancel generate", async ({ page, request }) => {
  const { projectId, chapterId } = await setupProjectAndChapter(request);

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);
  await expect(page.getByRole("textbox", { name: "标题", exact: true })).toHaveValue("E2E 第一章", { timeout: 60_000 });
  const content = page.locator('textarea[name="content_md"]');
  await expect(content).toBeVisible();

  const drawer = await openAiDrawer(page);
  await drawer.getByRole("checkbox", { name: "流式生成（beta）" }).uncheck();

  const dirtyMarker = "E2E_DIRTY_CANCEL";
  await content.fill(dirtyMarker);
  await expect(drawer.getByRole("button", { name: "保存", exact: true })).toBeEnabled();

  const genReqP = page
    .waitForRequest((req) => req.method() === "POST" && req.url().endsWith(`/api/chapters/${chapterId}/generate`), {
      timeout: 700,
    })
    .then(() => true)
    .catch(() => false);

  await drawer.getByRole("button", { name: "生成", exact: true }).click();
  const confirm = page.getByRole("dialog", { name: "章节有未保存修改，如何生成？", exact: true });
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", { name: "取消", exact: true }).click();

  expect(await genReqP).toBe(false);

  await expect(content).toHaveValue(new RegExp(dirtyMarker));
});
