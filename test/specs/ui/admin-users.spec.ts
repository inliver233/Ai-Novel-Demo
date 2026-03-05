import { test, expect } from "../../lib/ui-test";

test("ui: admin users page copy-once password flow is safe", async ({
  page,
}) => {
  const loginRes = await page.request.post("/api/auth/local/login", {
    data: { user_id: "admin", password: "admin-pass" },
  });
  expect(loginRes.ok()).toBeTruthy();

  await page.goto("/admin/users");

  await expect(page.getByText("管理员用户管理", { exact: true })).toBeVisible();
  await expect(page.getByText("创建用户", { exact: true })).toBeVisible();
  await expect(page.getByText("在线用户", { exact: true })).toBeVisible();
  await expect(page.getByText("累计调用次数（LLM API）", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("columnheader", { name: "一次性密码", exact: true }),
  ).toBeVisible();

  const userId = `e2e-user-${Date.now()}`;
  const displayName = "E2E 普通用户";

  await page.getByLabel("用户 ID（user_id）", { exact: true }).fill(userId);
  await page
    .getByLabel("显示名（display_name）", { exact: true })
    .fill(displayName);
  await page.getByRole("button", { name: "创建", exact: true }).click();

  const row = page.locator("tbody tr", { hasText: userId });
  await expect(row).toBeVisible({ timeout: 60_000 });
  await expect(
    row.getByRole("button", { name: "复制并隐藏", exact: true }),
  ).toBeVisible();

  // Responsive guard: mobile should not force horizontal scrolling.
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(row).not.toBeVisible();
  const cards = page.getByLabel("admin_users_cards", { exact: true });
  const card = cards.locator("div.rounded-atelier", { hasText: userId });
  await expect(card).toBeVisible();

  const overflow = await page.evaluate(() => {
    const el = document.documentElement;
    return { scrollWidth: el.scrollWidth, clientWidth: el.clientWidth };
  });
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 1);
});
