import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: writing can save and status persists", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const createChapterRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 保存状态", plan: "" },
  });
  expect(createChapterRes.ok()).toBeTruthy();
  const createChapterJson = (await createChapterRes.json()) as { ok: boolean; data: { chapter: { id: string } } };
  const chapterId = createChapterJson.data.chapter.id;

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);
  await expect(page.getByRole("textbox", { name: "标题", exact: true })).toHaveValue("E2E 保存状态", { timeout: 60_000 });

  const content = page.locator('textarea[name="content_md"]');
  await expect(content).toBeVisible();

  const dirtyBadge = page.getByText("（未保存）", { exact: true });
  await expect(dirtyBadge).toBeHidden();

  const marker = `E2E_SAVE_${Date.now()}`;
  await content.fill(marker);
  await expect(dirtyBadge).toBeVisible();

  const saveReqP1 = page.waitForRequest((req) => req.method() === "PUT" && req.url().endsWith(`/api/chapters/${chapterId}`));
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await saveReqP1;
  await expect(dirtyBadge).toBeHidden();

  const statusSelect = page.locator('select[name="status"]');
  await statusSelect.selectOption("done");
  await expect(dirtyBadge).toBeVisible();

  const saveReqP2 = page.waitForRequest((req) => req.method() === "PUT" && req.url().endsWith(`/api/chapters/${chapterId}`));
  await page.getByRole("button", { name: "保存", exact: true }).click();
  const saveReq2 = await saveReqP2;
  expect((saveReq2.postDataJSON() as { status?: string }).status).toBe("done");
  await expect(dirtyBadge).toBeHidden();

  await page.reload();
  await expect(page.getByRole("textbox", { name: "标题", exact: true })).toHaveValue("E2E 保存状态", { timeout: 60_000 });
  await expect(page.locator('select[name="status"]')).toHaveValue("done");
});

