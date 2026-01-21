import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

test("ui: prompt studio render preview + edit/save block", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  await page.goto(`/projects/${projectId}/prompt-studio`);
  await expect(page.getByText("提示词工作室（beta）")).toBeVisible();

  // Pick a preset that actually supports the preview task, otherwise preview can be empty.
  await page.getByRole("button", { name: /chapter_generate/ }).first().click();

  const previewPanel = page.locator(".panel", { has: page.getByText("预览（后端渲染）") });
  const renderPreview = previewPanel.getByRole("button", { name: "渲染预览", exact: true });
  await expect(renderPreview).toBeEnabled({ timeout: 60_000 });

  await Promise.all([
    page.waitForResponse((resp) => resp.request().method() === "POST" && resp.url().includes(`/api/projects/${projectId}/prompt_preview`)),
    renderPreview.click(),
  ]);
  await expect(previewPanel.getByText("Token 估算")).toBeVisible({ timeout: 60_000 });

  const systemTa = previewPanel.locator("textarea[readonly]").nth(0);
  const userTa = previewPanel.locator("textarea[readonly]").nth(1);
  await expect.poll(async () => (await systemTa.inputValue()).trim().length + (await userTa.inputValue()).trim().length).toBeGreaterThan(0);

  const marker = "E2E_PROMPT_STUDIO_MARKER";
  const blocksPanel = page.locator(".panel", { has: page.getByText("提示块") });
  const previewTask = "chapter_generate";
  const surfaces = blocksPanel.locator(".surface");
  let target = surfaces.first();
  const maxScan = Math.min(await surfaces.count(), 12);
  for (let i = 0; i < maxScan; i += 1) {
    const s = surfaces.nth(i);
    const checkbox = s.getByRole("checkbox").first();
    const enabled = await checkbox.isChecked();
    if (!enabled) continue;
    const role = await s.getByRole("combobox").first().inputValue();
    if (role !== "system" && role !== "user") continue;
    const triggersValue = (await s.getByPlaceholder("chapter_generate, outline_generate").inputValue()).trim();
    const triggers = triggersValue
      ? triggersValue.split(",").map((x) => x.trim()).filter(Boolean)
      : [];
    if (triggers.length === 0 || triggers.includes(previewTask)) {
      target = s;
      break;
    }
  }

  const enabledCheckbox = target.getByRole("checkbox").first();
  if (!(await enabledCheckbox.isChecked())) await enabledCheckbox.check();

  const triggersInput = target.getByPlaceholder("chapter_generate, outline_generate");
  const triggersRaw = (await triggersInput.inputValue()).trim();
  if (triggersRaw && !triggersRaw.split(",").map((x) => x.trim()).includes(previewTask)) {
    await triggersInput.fill(previewTask);
  }

  const templateTa = target.locator("textarea").first();
  const originalTemplate = await templateTa.inputValue();
  await templateTa.fill(`${originalTemplate}\n\n${marker}`);
  await Promise.all([
    page.waitForResponse((resp) => resp.request().method() === "PUT" && resp.url().includes("/api/prompt_blocks/") && resp.ok()),
    target.getByRole("button", { name: "保存", exact: true }).click(),
  ]);

  await Promise.all([
    page.waitForResponse((resp) => resp.request().method() === "POST" && resp.url().includes(`/api/projects/${projectId}/prompt_preview`)),
    renderPreview.click(),
  ]);
  await expect.poll(async () => {
    const s = await systemTa.inputValue();
    const u = await userTa.inputValue();
    return s.includes(marker) || u.includes(marker);
  }).toBe(true);
});
