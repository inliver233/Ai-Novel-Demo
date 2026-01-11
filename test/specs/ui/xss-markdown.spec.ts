import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: markdown must not execute raw HTML (XSS guard)", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const bulk = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters/bulk_create`, {
    data: {
      chapters: [{ number: 1, title: "XSS chapter", plan: "" }],
    },
  });
  expect(bulk.ok()).toBeTruthy();
  const bulkJson = (await bulk.json()) as { ok: boolean; data: { chapters: Array<{ id: string; number: number }> } };
  const chapterId = bulkJson.data.chapters[0]?.id;
  expect(chapterId).toBeTruthy();

  const payload = [
    "# XSS guard",
    "",
    '<img src=x onerror=alert("xss-img")>',
    "",
    '[xss-link](javascript:alert("xss-link"))',
  ].join("\n");

  const put = await request.put(`${state.backendUrl}/api/chapters/${chapterId}`, {
    data: { content_md: payload, status: "drafting" },
  });
  expect(put.ok()).toBeTruthy();

  const installDialogFailFast = (p: typeof page) => {
    p.on("dialog", (dialog) => {
      const msg = `${dialog.type()}: ${dialog.message()}`;
      void dialog.dismiss();
      throw new Error(`Unexpected dialog triggered (possible XSS): ${msg}`);
    });
  };
  installDialogFailFast(page);

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);
  await expect(page.locator('textarea[name="content_md"]')).toHaveValue(payload);
  await page.getByRole("button", { name: "预览", exact: true }).click();

  const editorLink = page.getByRole("link", { name: "xss-link", exact: true });
  await expect(editorLink).toBeVisible();
  await expect(editorLink).not.toHaveAttribute("href", /^javascript:/);
  await expect(page.locator('img[src="x"]')).toHaveCount(0);

  const previewPage = await page.context().newPage();
  installDialogFailFast(previewPage);
  await previewPage.goto(`/projects/${projectId}/preview`);

  const previewLink = previewPage.getByRole("link", { name: "xss-link", exact: true });
  await expect(previewLink).toBeVisible();
  await expect(previewLink).not.toHaveAttribute("href", /^javascript:/);
  await expect(previewPage.locator('img[src="x"]')).toHaveCount(0);
});
