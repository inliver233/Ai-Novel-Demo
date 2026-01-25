import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

test("ui: prompt-templates list items should not overflow", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  await page.goto(`/projects/${projectId}/prompt-templates`);

  const listPanelHeading = page.getByText("系统默认模板", { exact: true });
  await expect(listPanelHeading).toBeVisible();

  const listPanel = listPanelHeading.locator("..");
  const buttons = listPanel.locator("button");
  await expect(buttons.first()).toBeVisible();

  const count = await buttons.count();
  expect(count).toBeGreaterThan(0);

  for (let i = 0; i < count; i += 1) {
    const button = buttons.nth(i);
    const metrics = await button.evaluate((el) => ({
      clientWidth: el.clientWidth,
      scrollWidth: el.scrollWidth,
    }));

    expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.clientWidth + 1);
  }
});

