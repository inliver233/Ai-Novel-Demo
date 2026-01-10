import { test, expect } from "../../lib/ui-test";

test("ui: create project from dashboard", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "+ 新建项目", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "创建项目" })).toBeVisible();

  await page.getByLabel("项目名", { exact: true }).fill("UI Create Project");
  await page.getByRole("button", { name: "创建", exact: true }).click();

  await page.waitForURL(/\/projects\/[^/]+\/settings$/, { timeout: 60_000 });
  await expect(page.getByText("项目信息")).toBeVisible();
});
