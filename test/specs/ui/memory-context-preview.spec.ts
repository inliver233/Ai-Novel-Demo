import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

test("ui: writing page opens ContextPreviewDrawer", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  await page.goto(`/projects/${projectId}/writing`);
  await expect(page.getByRole("button", { name: "上下文预览", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "上下文预览", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "上下文预览" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("MemoryContextPack / logs")).toBeVisible();
  await expect(dialog.getByText("worldbook", { exact: true })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "关闭", exact: true })).toBeVisible();
});
