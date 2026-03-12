import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("ui: select style -> generate + post_edit_sanitize -> replay style_resolution", async ({ page, request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const create = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters`, {
    data: { number: 1, title: "E2E 第一章", plan: "" },
  });
  expect(create.ok()).toBeTruthy();
  const createJson = (await create.json()) as ApiOk<{ chapter: { id: string } }>;
  const chapterId = createJson.data.chapter.id;

  const styleRes = await request.post(`${state.backendUrl}/api/writing_styles`, {
    data: {
      name: "E2E 注入风格",
      description: "for style injection test",
      prompt_content: "写作要求：\n- E2E 风格注入\n- 句子更克制\n",
    },
  });
  expect(styleRes.ok()).toBeTruthy();
  const styleJson = (await styleRes.json()) as ApiOk<{ style: { id: string } }>;
  const styleId = styleJson.data.style.id;

  await page.goto(`/projects/${projectId}/writing?chapterId=${chapterId}`);
  await page.getByRole("button", { name: /AI/ }).click();
  const drawer = page.getByRole("dialog", { name: "AI 生成", exact: true });
  await expect(drawer).toBeVisible();

  await drawer.getByRole("button", { name: "高级参数", exact: true }).click();
  await drawer.getByRole("checkbox", { name: "流式生成（beta）", exact: true }).uncheck();
  await drawer.getByRole("checkbox", { name: "润色", exact: true }).check();
  await drawer.getByRole("checkbox", { name: "去味/一致性修复", exact: true }).check();
  await expect(page.getByText("已为规划/润色/正文优化自动启用可靠链路，避免请求超时。")).toBeVisible();

  const styleSelect = drawer.getByLabel("gen_style_id", { exact: true });
  await expect(styleSelect).toBeVisible();
  await expect(styleSelect.locator(`option[value="${styleId}"]`)).toHaveCount(1);
  await styleSelect.selectOption(styleId);

  let sawNonStreamGenerate = false;
  await page.route(`**/api/chapters/${chapterId}/generate`, async (route) => {
    sawNonStreamGenerate = true;
    await route.fallback();
  });
  const genReqP = page.waitForRequest(
    (req) => req.method() === "POST" && req.url().endsWith(`/api/chapters/${chapterId}/generate-stream`),
  );
  await drawer.getByRole("button", { name: "生成", exact: true }).click();
  await genReqP;
  await expect(page.locator('textarea[name="content_md"]')).not.toHaveValue("", { timeout: 60_000 });
  expect(sawNonStreamGenerate).toBe(false);

  const postEditCompareButton = drawer.getByRole("button", { name: "润色对比/回退", exact: true });
  await expect(postEditCompareButton).toBeVisible({ timeout: 60_000 });
  await postEditCompareButton.click();
  const compare = page.getByRole("dialog", { name: "润色对比", exact: true });
  await expect(compare).toBeVisible();
  await compare.getByRole("button", { name: "后处理稿", exact: true }).click();
  await expect(compare).toContainText("E2E 润色校验已完成");
  await expect(compare).toContainText("E2E 风格注入已生效");
  await compare.getByRole("button", { name: "关闭", exact: true }).click();

  await drawer.getByRole("button", { name: "关闭", exact: true }).click();

  const openHistory = page.getByLabel("Open generation history (writing_open_generation_history)", { exact: true });
  await expect(openHistory).toBeVisible({ timeout: 60_000 });
  await openHistory.click();
  const history = page.getByRole("dialog", { name: "生成记录", exact: true });
  await expect(history).toBeVisible();

  await expect(history).toContainText(styleId);
  await expect(history).toContainText('"source": "request"');

  const postEditPipelineButton = history.locator('button[aria-label^="pipeline run_id:"]').filter({
    hasText: "post_edit_sanitize",
  });
  await expect(postEditPipelineButton).toHaveCount(1, { timeout: 60_000 });
  await postEditPipelineButton.first().click();
  await expect(history).toContainText('"post_edit_sanitize": true');
});
