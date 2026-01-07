import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("ui: preview navigation (buttons/keyboard) + edit jump", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const bulk = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters/bulk_create`, {
    data: {
      chapters: [
        { number: 1, title: "第 1 章", plan: "" },
        { number: 2, title: "第 2 章", plan: "" },
        { number: 3, title: "第 3 章", plan: "" },
      ],
    },
  });
  expect(bulk.ok()).toBeTruthy();
  const bulkJson = (await bulk.json()) as { ok: boolean; data: { chapters: Array<{ id: string; number: number }> } };
  const byNumber = new Map(bulkJson.data.chapters.map((c) => [c.number, c.id]));
  const chapter1Id = byNumber.get(1);
  const chapter2Id = byNumber.get(2);
  const chapter3Id = byNumber.get(3);
  expect(chapter1Id).toBeTruthy();
  expect(chapter2Id).toBeTruthy();
  expect(chapter3Id).toBeTruthy();

  for (const n of [1, 2, 3]) {
    const id = byNumber.get(n)!;
    const put = await request.put(`${state.backendUrl}/api/chapters/${id}`, {
      data: { content_md: `# E2E Chapter ${n}\n\n内容 ${n}`, status: "done" },
    });
    expect(put.ok()).toBeTruthy();
  }

  await page.goto(`/projects/${projectId}/preview`);

  const prevBtn = page.getByRole("button", { name: "上一章", exact: true });
  const nextBtn = page.getByRole("button", { name: "下一章", exact: true });

  await expect(page.getByText("正在预览：第 1 章", { exact: true })).toBeVisible();
  await expect(prevBtn).toBeDisabled();
  await expect(nextBtn).toBeEnabled();

  await nextBtn.click();
  await expect(page.getByText("正在预览：第 2 章", { exact: true })).toBeVisible();
  await expect(prevBtn).toBeEnabled();
  await expect(nextBtn).toBeEnabled();

  await page.keyboard.press("ArrowRight");
  await expect(page.getByText("正在预览：第 3 章", { exact: true })).toBeVisible();
  await expect(prevBtn).toBeEnabled();
  await expect(nextBtn).toBeDisabled();

  await page.keyboard.press("ArrowLeft");
  await expect(page.getByText("正在预览：第 2 章", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/writing\\?chapterId=${chapter2Id}$`));
});

