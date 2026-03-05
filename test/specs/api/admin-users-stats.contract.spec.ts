import { test, expect } from "@playwright/test";

import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("api: admin users endpoint returns paginated stats summary", async ({ request }) => {
  const state = loadState();

  const login = await request.post(`${state.backendUrl}/api/auth/local/login`, {
    data: { user_id: "admin", password: "admin-pass" },
  });
  expect(login.ok()).toBeTruthy();

  const suffix = Date.now();
  for (const userId of [`stats-user-a-${suffix}`, `stats-user-b-${suffix}`]) {
    const create = await request.post(`${state.backendUrl}/api/auth/admin/users`, {
      data: {
        user_id: userId,
        display_name: userId,
        password: "password-123",
      },
    });
    expect(create.ok()).toBeTruthy();
  }

  const first = await request.get(`${state.backendUrl}/api/auth/admin/users?limit=1`);
  expect(first.ok()).toBeTruthy();
  const firstJson = (await first.json()) as ApiOk<{
    users: Array<Record<string, unknown>>;
    summary: Record<string, unknown>;
    pagination: { next_cursor: string | null; has_more: boolean };
  }>;
  expect(firstJson.ok).toBe(true);
  expect(Array.isArray(firstJson.data.users)).toBeTruthy();
  expect(typeof firstJson.data.summary.total_users).toBe("number");
  expect(typeof firstJson.data.summary.total_online_users).toBe("number");
  expect(typeof firstJson.data.summary.total_generation_calls).toBe("number");
  expect(typeof firstJson.data.summary.total_generated_chars).toBe("number");
  expect(typeof firstJson.data.summary.online_window_seconds).toBe("number");
  expect(typeof firstJson.data.pagination.has_more).toBe("boolean");

  if (firstJson.data.pagination.has_more && firstJson.data.pagination.next_cursor) {
    const second = await request.get(
      `${state.backendUrl}/api/auth/admin/users?limit=1&cursor=${encodeURIComponent(firstJson.data.pagination.next_cursor)}`,
    );
    expect(second.ok()).toBeTruthy();
    const secondJson = (await second.json()) as ApiOk<{ users: Array<{ id: string }> }>;
    expect(secondJson.ok).toBe(true);
    expect(Array.isArray(secondJson.data.users)).toBeTruthy();
    if (firstJson.data.users.length > 0 && secondJson.data.users.length > 0) {
      expect(secondJson.data.users[0].id).not.toBe(String(firstJson.data.users[0].id));
    }
  }

  const query = await request.get(`${state.backendUrl}/api/auth/admin/users?limit=50&q=${encodeURIComponent(`stats-user-a-${suffix}`)}`);
  expect(query.ok()).toBeTruthy();
  const queryJson = (await query.json()) as ApiOk<{
    users: Array<{ id: string }>;
    summary: { filtered_total_users: number; total_users: number };
  }>;
  expect(queryJson.ok).toBe(true);
  expect(queryJson.data.summary.filtered_total_users).toBeGreaterThanOrEqual(1);
  expect(queryJson.data.summary.total_users).toBeGreaterThanOrEqual(queryJson.data.summary.filtered_total_users);
  expect(queryJson.data.users.some((u) => u.id === `stats-user-a-${suffix}`)).toBeTruthy();
});
