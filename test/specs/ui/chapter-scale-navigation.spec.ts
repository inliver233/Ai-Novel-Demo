import { expect, test } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: large chapter lists stay windowed and keep active navigation intact", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const chapters = Array.from({ length: 180 }, (_, index) => ({
    number: index + 1,
    title: `Scale Chapter ${index + 1}`,
    plan: `Scale plan ${index + 1}`,
  }));

  const bulk = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters/bulk_create`, {
    data: { chapters },
  });
  expect(bulk.ok()).toBeTruthy();
  const bulkJson = (await bulk.json()) as { ok: boolean; data: { chapters: Array<{ id: string; number: number }> } };
  const byNumber = new Map(bulkJson.data.chapters.map((chapter) => [chapter.number, chapter.id]));

  const chapter1Id = byNumber.get(1);
  const chapter120Id = byNumber.get(120);
  const chapter180Id = byNumber.get(180);
  expect(chapter1Id).toBeTruthy();
  expect(chapter120Id).toBeTruthy();
  expect(chapter180Id).toBeTruthy();

  const seedTargets = [
    { id: chapter1Id!, number: 1, status: "done" as const },
    { id: chapter120Id!, number: 120, status: "drafting" as const },
    { id: chapter180Id!, number: 180, status: "done" as const },
  ];

  for (const target of seedTargets) {
    const update = await request.put(`${state.backendUrl}/api/chapters/${target.id}`, {
      data: {
        content_md: `# Scale Chapter ${target.number}\n\nScale content ${target.number}`,
        summary: `Scale summary ${target.number}`,
        status: target.status,
      },
    });
    expect(update.ok()).toBeTruthy();
  }

  const chapterListLabel = "章节列表";

  await page.goto(`/projects/${projectId}/preview`);
  await expect(page.getByText("正在预览：第 1 章", { exact: false })).toBeVisible();

  const previewListItems = page.locator(`[role="list"][aria-label="${chapterListLabel}"] [role="listitem"]`);
  await expect(previewListItems.first()).toBeVisible();
  expect(await previewListItems.count()).toBeLessThan(40);
  await expect(page.getByRole("button", { name: /^180\. Scale Chapter 180/, exact: false })).toHaveCount(0);

  await page.goto(`/projects/${projectId}/reader?chapterId=${chapter180Id}`);
  await expect(page.getByText("正在阅读：第 180 章", { exact: false })).toBeVisible();

  const readerListItems = page.locator(`[role="list"][aria-label="${chapterListLabel}"] [role="listitem"]`);
  await expect(readerListItems.first()).toBeVisible();
  expect(await readerListItems.count()).toBeLessThan(40);
  await expect(page.locator(`[role="list"][aria-label="${chapterListLabel}"] button[aria-current="true"]`)).toContainText(
    "180. Scale Chapter 180",
  );

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/projects/${projectId}/writing?chapterId=${chapter120Id}`);
  await expect(page.getByRole("textbox", { name: "标题", exact: true })).toHaveValue("Scale Chapter 120", {
    timeout: 60_000,
  });

  await page.getByRole("button", { name: chapterListLabel, exact: true }).click();
  const chapterDrawer = page.getByRole("dialog", { name: chapterListLabel, exact: true });
  await expect(chapterDrawer).toBeVisible();

  const drawerListItems = chapterDrawer.locator(`[role="list"][aria-label="${chapterListLabel}"] [role="listitem"]`);
  await expect(drawerListItems.first()).toBeVisible();
  expect(await drawerListItems.count()).toBeLessThan(40);
  await expect(chapterDrawer.locator(`[role="list"][aria-label="${chapterListLabel}"] button[aria-current="true"]`)).toContainText(
    "#120",
  );
});
