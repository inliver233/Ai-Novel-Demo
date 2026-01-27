import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

test("ui: chapter stream generation updates editor", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  await page.goto(`/projects/${projectId}/writing`);
  await expect(page.getByRole("button", { name: "新增章节" })).toBeVisible();

  await page.getByRole("button", { name: "新增章节" }).click();
  await expect(page.getByRole("dialog", { name: "新增章节" })).toBeVisible();

  await page.locator('input[name="number"]').fill("1");
  await page.locator('input[name="title"]').fill("E2E 第一章");
  await page.locator('textarea[name="plan"]').fill("要点 A；要点 B");
  await page.getByRole("button", { name: "创建", exact: true }).click();

  await expect(page.getByRole("button", { name: "AI 生成" })).toBeVisible();
  await page.getByRole("button", { name: "AI 生成" }).click();
  const drawer = page.getByRole("dialog", { name: "AI 生成" });
  await expect(drawer).toBeVisible();

  await drawer.getByRole("button", { name: "高级参数", exact: true }).click();
  const streamCheckbox = drawer.getByRole("checkbox", { name: "流式生成（beta）", exact: true });
  await streamCheckbox.check();

  const content = page.locator('textarea[name="content_md"]');
  await expect(content).toHaveValue("");

  await page.evaluate(() => {
    // @ts-ignore
    window.__e2eContentValueLens = [];
    const el = document.querySelector('textarea[name="content_md"]');
    if (!el) return;
    // @ts-ignore
    window.__e2eContentValueLens.push(String((el as HTMLTextAreaElement).value ?? "").length);
    const desc = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
    if (!desc?.get || !desc?.set) return;
    const originalGet = desc.get;
    const originalSet = desc.set;
    Object.defineProperty(el, "value", {
      get() {
        // @ts-ignore
        return originalGet.call(this);
      },
      set(v) {
        // @ts-ignore
        window.__e2eContentValueLens.push(String(v ?? "").length);
        // @ts-ignore
        originalSet.call(this, v);
      },
    });
  });

  await drawer.getByRole("button", { name: "生成", exact: true }).click();

  await expect(content).not.toHaveValue("", { timeout: 30_000 });
  await expect(content).toContainText("E2E");

  const lens = (await page.evaluate(() => {
    // @ts-ignore
    return window.__e2eContentValueLens || [];
  })) as number[];
  let increases = 0;
  for (let i = 1; i < lens.length; i += 1) {
    if (lens[i] > lens[i - 1]) increases += 1;
  }
  expect(increases).toBeGreaterThanOrEqual(2);
});
