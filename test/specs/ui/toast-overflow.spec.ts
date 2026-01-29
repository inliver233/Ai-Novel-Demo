import { test, expect } from "../../lib/ui-test";

async function expectNoHorizontalOverflow(locator: import("@playwright/test").Locator) {
  await expect(locator).toBeVisible();
  const metrics = await locator.evaluate((el) => ({
    clientWidth: (el as HTMLElement).clientWidth,
    scrollWidth: (el as HTMLElement).scrollWidth,
  }));
  expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.clientWidth);
}

test("ui: toast does not overflow on long message + request_id", async ({ page }) => {
  const longMessage = `TOAST_OVERFLOW_${"x".repeat(420)}`;
  const longRequestId = `req_${"9".repeat(160)}`;

  await page.route("**/api/auth/local/login", async (route) => {
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({
        ok: false,
        error: { code: "E2E_TOAST_OVERFLOW", message: longMessage },
        request_id: longRequestId,
      }),
    });
  });

  await page.goto("/login");

  await page.getByLabel("用户名", { exact: true }).fill("admin");
  await page.getByLabel("密码", { exact: true }).fill("admin-pass");
  await page.getByRole("button", { name: "登录", exact: true }).click();

  const toastStack = page.getByRole("status");
  const closeToastButton = toastStack.getByRole("button", { name: "关闭提示", exact: true });
  await expect(closeToastButton).toBeVisible();

  const toastCard = closeToastButton.locator('xpath=ancestor::*[contains(@class,"rounded-atelier")][1]');
  await expect(toastCard).toContainText("E2E_TOAST_OVERFLOW");

  const copyRequestIdButton = toastCard.getByLabel("copy_request_id", { exact: true });
  await expect(copyRequestIdButton).toBeVisible();
  await copyRequestIdButton.click();

  const requestIdBadge = copyRequestIdButton.locator('xpath=ancestor::div[contains(@class,"rounded-atelier")][1]');
  await expectNoHorizontalOverflow(toastCard);
  await expectNoHorizontalOverflow(requestIdBadge);
});

