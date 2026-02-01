import { test, expect } from "../../lib/ui-test";

import type { APIRequestContext } from "@playwright/test";

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

test("ui: writing done is explicit (no silent revert, readonly after save)", async ({ page, request }) => {
  const { projectId, chapterId } = await setupProjectAndChapter(request);

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);

  const title = page.getByRole("textbox", { name: "标题", exact: true });
  await expect(title).toHaveValue("E2E 第一章", { timeout: 60_000 });

  const statusSelect = page.locator('select[name="status"]');
  await statusSelect.selectOption("done");

  await title.fill("E2E_DONE_TITLE");
  await expect(statusSelect).toHaveValue("done");

  const saveReqP = page.waitForRequest(
    (req) => req.method() === "PUT" && req.url().endsWith(`/api/chapters/${chapterId}`),
  );
  await page.getByRole("button", { name: "保存", exact: true }).click();

  const saveReq = await saveReqP;
  const saveBody = saveReq.postDataJSON() as { status?: string };
  expect(saveBody.status).toBe("done");

  const callout = page.locator(".callout-warning").filter({ hasText: "本章已定稿" });
  await expect(callout).toBeVisible();
  await expect(title).not.toBeEditable();

  await callout.getByRole("button", { name: /回退为/ }).click();
  await expect(statusSelect).toHaveValue("drafting");
  await expect(title).toBeEditable();
  await expect(callout).toBeHidden();
});

