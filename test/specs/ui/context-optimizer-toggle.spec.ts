import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

test("ui: settings context_optimizer_enabled toggles and ContextPreviewDrawer shows status", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  const expandSettingsSection = async (title: string) => {
    const summary = page.locator("summary", { hasText: title });
    await expect(summary).toBeVisible();
    const details = summary.locator("..");
    if ((await details.getAttribute("open")) === null) {
      await summary.click();
      await expect(details).toHaveAttribute("open", "");
    }
  };

  const openContextPreview = async () => {
    await page.goto(`/projects/${projectId}/writing`);
    await page.getByRole("button", { name: "上下文预览", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "上下文预览" });
    await expect(dialog).toBeVisible();
    const injectionToggle = dialog.getByRole("checkbox", { name: "世界书注入", exact: true });
    await injectionToggle.check();
    await expect(dialog.getByText("Pack sections", { exact: true })).toBeVisible();
    await expect(dialog.getByText("Context Optimizer", { exact: true })).toBeVisible();
    return dialog;
  };

  await page.goto(`/projects/${projectId}/settings`);
  await expect(page.getByText("上下文优化（Context Optimizer）", { exact: true })).toBeVisible();
  await expandSettingsSection("上下文优化（Context Optimizer）");

  const getToggle = () => page.getByRole("checkbox", { name: "启用 ContextOptimizer（影响 Prompt 预览与生成）", exact: true });
  const save = page.getByRole("button", { name: "保存", exact: true });

  await getToggle().check();
  await expect(save).toBeEnabled();
  const enableRes = page.waitForResponse(
    (resp) => resp.request().method() === "PUT" && resp.url().includes(`/api/projects/${projectId}/settings`) && resp.ok(),
  );
  await Promise.all([enableRes, save.click()]);
  await expect(save).toBeDisabled();

  const enabledDialog = await openContextPreview();
  await expect(enabledDialog.getByText("status: enabled", { exact: true })).toBeVisible();
  await expect(enabledDialog.getByText(/saved_tokens_estimate:/)).toBeVisible();

  await page.goto(`/projects/${projectId}/settings`);
  await expandSettingsSection("上下文优化（Context Optimizer）");
  await getToggle().uncheck();
  await expect(save).toBeEnabled();
  const disableRes = page.waitForResponse(
    (resp) => resp.request().method() === "PUT" && resp.url().includes(`/api/projects/${projectId}/settings`) && resp.ok(),
  );
  await Promise.all([disableRes, save.click()]);
  await expect(save).toBeDisabled();

  const disabledDialog = await openContextPreview();
  await expect(disabledDialog.getByText("status: disabled", { exact: true })).toBeVisible();
  await expect(disabledDialog.getByText("未启用时不会执行对比请求。可在 SettingsPage 开启后再查看摘要与 diff。", { exact: true })).toBeVisible();
});
