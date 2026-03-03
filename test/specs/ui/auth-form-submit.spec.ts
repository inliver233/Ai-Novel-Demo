import { expect, test } from "../../lib/ui-test";

const SESSION_EXPIRE_AT = Math.floor(Date.now() / 1000) + 3600;

test("ui: login submits on Enter key in password field", async ({ page }) => {
  let loginSubmitCount = 0;
  await page.route("**/api/auth/local/login", async (route) => {
    loginSubmitCount += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        data: {
          user: { id: "enter-login-user", display_name: "Enter Login User", is_admin: false },
          session: { expire_at: SESSION_EXPIRE_AT },
        },
      }),
    });
  });

  await page.goto("/login");
  await page.getByLabel("用户名", { exact: true }).fill("enter-login-user");
  const password = page.getByLabel("密码", { exact: true });
  await password.fill("password-123");

  const loginResponse = page.waitForResponse(
    (response) => response.url().includes("/api/auth/local/login") && response.request().method() === "POST",
  );
  await password.press("Enter");

  const loginResponseValue = await loginResponse;
  expect(loginResponseValue.ok()).toBeTruthy();
  await expect.poll(() => loginSubmitCount).toBe(1);
});

test("ui: register submits on Enter key in confirm password field", async ({ page }) => {
  let registerSubmitCount = 0;
  await page.route("**/api/auth/local/register", async (route) => {
    registerSubmitCount += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        data: {
          user: { id: "enter-register-user", display_name: "Enter Register User", is_admin: false },
          session: { expire_at: SESSION_EXPIRE_AT },
        },
      }),
    });
  });

  await page.goto("/register");
  await page.getByLabel("用户名", { exact: true }).fill("enter-register-user");
  await page.getByLabel("密码", { exact: true }).fill("password-123");
  const confirmPassword = page.getByLabel("确认密码", { exact: true });
  await confirmPassword.fill("password-123");

  const registerResponse = page.waitForResponse(
    (response) => response.url().includes("/api/auth/local/register") && response.request().method() === "POST",
  );
  await confirmPassword.press("Enter");

  const registerResponseValue = await registerResponse;
  expect(registerResponseValue.ok()).toBeTruthy();
  await expect.poll(() => registerSubmitCount).toBe(1);
});
