import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

test("ui: prompt studio drag reorder calls backend and updates order", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  await page.goto(`/projects/${projectId}/prompt-studio`);
  await expect(page.getByText("提示词工作室（beta）")).toBeVisible();

  await page.getByRole("button", { name: /chapter_generate/ }).first().click();

  const blocksPanel = page.locator(".panel", { has: page.getByText("提示块") });
  const surfaces = blocksPanel.locator(".surface");
  await expect(surfaces.first()).toBeVisible();
  expect(await surfaces.count()).toBeGreaterThan(1);

  const firstName = (await surfaces.nth(0).locator(".font-semibold").first().innerText()).trim();
  const secondName = (await surfaces.nth(1).locator(".font-semibold").first().innerText()).trim();
  expect(firstName.length).toBeGreaterThan(0);
  expect(secondName.length).toBeGreaterThan(0);

  const reorderResp = page.waitForResponse((resp) => {
    return (
      resp.request().method() === "POST" &&
      resp.url().includes("/api/prompt_presets/") &&
      resp.url().endsWith("/blocks/reorder") &&
      resp.ok()
    );
  });

  // Drag the second block onto the first to force an order change.
  await surfaces.nth(1).dispatchEvent("dragstart");
  await surfaces.nth(0).dispatchEvent("dragover");
  await surfaces.nth(0).dispatchEvent("drop");
  await reorderResp;

  const nextFirstName = (await blocksPanel.locator(".surface").nth(0).locator(".font-semibold").first().innerText()).trim();
  expect(nextFirstName).toBe(secondName);
});
