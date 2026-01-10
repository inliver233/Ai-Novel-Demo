import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };
type ApiErr = { ok: false; error: { code: string; message: string; details?: unknown }; request_id: string };

test("api: auth/user returns 401 when not logged in", async ({ request }) => {
  const state = loadState();

  const res = await request.get(`${state.backendUrl}/api/auth/user`);
  expect(res.status()).toBe(401);
  expect(res.headers()["x-request-id"]).toBeTruthy();

  const json = (await res.json()) as ApiErr;
  expect(json.ok).toBe(false);
  expect(json.error.code).toBe("UNAUTHORIZED");
  expect(typeof json.request_id).toBe("string");
  expect(json.request_id.length).toBeGreaterThan(0);
});

test("api: refresh returns 401 when not logged in", async ({ request }) => {
  const state = loadState();

  const res = await request.post(`${state.backendUrl}/api/auth/refresh`);
  expect(res.status()).toBe(401);
  expect(res.headers()["x-request-id"]).toBeTruthy();
});

test("api: login sets session cookie and enables auth/user", async ({ request }) => {
  const state = loadState();

  const login = await request.post(`${state.backendUrl}/api/auth/local/login`, {
    data: { user_id: "admin", password: "admin-pass" },
  });
  expect(login.ok()).toBeTruthy();

  const setCookies = login
    .headersArray()
    .filter((h) => h.name.toLowerCase() === "set-cookie")
    .map((h) => h.value)
    .join("\n");
  expect(setCookies).toContain("user_id=");
  expect(setCookies).toContain("session_expire_at=");

  const loginJson = (await login.json()) as ApiOk<{ user: { id: string; is_admin: boolean } }>;
  expect(loginJson.ok).toBe(true);
  expect(loginJson.data.user.id).toBe("admin");
  expect(loginJson.data.user.is_admin).toBe(true);

  const me = await request.get(`${state.backendUrl}/api/auth/user`);
  expect(me.ok()).toBeTruthy();
  const meJson = (await me.json()) as ApiOk<{ user: { id: string } }>;
  expect(meJson.ok).toBe(true);
  expect(meJson.data.user.id).toBe("admin");

  const refresh = await request.post(`${state.backendUrl}/api/auth/refresh`);
  expect(refresh.ok()).toBeTruthy();
  const refreshJson = (await refresh.json()) as ApiOk<{ refreshed: boolean }>;
  expect(refreshJson.ok).toBe(true);
  expect(typeof refreshJson.data.refreshed).toBe("boolean");

  const logout = await request.post(`${state.backendUrl}/api/auth/logout`);
  expect(logout.ok()).toBeTruthy();
  const logoutJson = (await logout.json()) as ApiOk<Record<string, never>>;
  expect(logoutJson.ok).toBe(true);

  const afterLogout = await request.get(`${state.backendUrl}/api/auth/user`);
  expect(afterLogout.status()).toBe(401);
});

test("api: rbac forbids reading non-member project", async ({ request }) => {
  const state = loadState();

  const { projectId } = await bootstrapProject(request);

  const login = await request.post(`${state.backendUrl}/api/auth/local/login`, {
    data: { user_id: "admin", password: "admin-pass" },
  });
  expect(login.ok()).toBeTruthy();

  const res = await request.get(`${state.backendUrl}/api/projects/${projectId}`);
  expect(res.status()).toBe(403);
  expect(res.headers()["x-request-id"]).toBeTruthy();

  const json = (await res.json()) as ApiErr;
  expect(json.ok).toBe(false);
  expect(json.error.code).toBe("FORBIDDEN");
  expect(typeof json.request_id).toBe("string");
  expect(json.request_id.length).toBeGreaterThan(0);
});
