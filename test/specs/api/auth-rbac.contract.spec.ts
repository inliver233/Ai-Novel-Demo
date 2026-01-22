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

  const setCookiesList = login
    .headersArray()
    .filter((h) => h.name.toLowerCase() === "set-cookie")
    .map((h) => h.value);
  const setCookies = setCookiesList.join("\n");
  expect(setCookies).toContain("user_id=");
  expect(setCookies).toContain("session_expire_at=");
  const expireCookie = setCookiesList.find((line) => line.startsWith("session_expire_at="));
  expect(expireCookie).toBeTruthy();
  expect(expireCookie?.toLowerCase()).toContain("httponly");

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

test("api: rbac hides non-member project existence (404)", async ({ request }) => {
  const state = loadState();

  const { projectId } = await bootstrapProject(request);

  const login = await request.post(`${state.backendUrl}/api/auth/local/login`, {
    data: { user_id: "admin", password: "admin-pass" },
  });
  expect(login.ok()).toBeTruthy();

  const projectRes = await request.get(`${state.backendUrl}/api/projects/${projectId}`);
  expect(projectRes.status()).toBe(404);
  expect(projectRes.headers()["x-request-id"]).toBeTruthy();

  const projectJson = (await projectRes.json()) as ApiErr;
  expect(projectJson.ok).toBe(false);
  expect(projectJson.error.code).toBe("NOT_FOUND");
  expect(typeof projectJson.request_id).toBe("string");
  expect(projectJson.request_id.length).toBeGreaterThan(0);

  const presetRes = await request.get(`${state.backendUrl}/api/projects/${projectId}/llm_preset`);
  expect(presetRes.status()).toBe(404);
  const presetJson = (await presetRes.json()) as ApiErr;
  expect(presetJson.ok).toBe(false);
  expect(presetJson.error.code).toBe("NOT_FOUND");

  const updateRes = await request.put(`${state.backendUrl}/api/projects/${projectId}`, { data: {} });
  expect(updateRes.status()).toBe(404);
  const updateJson = (await updateRes.json()) as ApiErr;
  expect(updateJson.ok).toBe(false);
  expect(updateJson.error.code).toBe("NOT_FOUND");
});

test("api: project memberships manage access (viewer/editor/remove)", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  // As dev_fallback owner (local-user), invite admin as viewer.
  const invite = await request.post(`${state.backendUrl}/api/projects/${projectId}/memberships`, {
    data: { user_id: "admin", role: "viewer" },
  });
  expect(invite.ok()).toBeTruthy();

  // Admin becomes a viewer: can read project but cannot call editor-only routes.
  const loginAsAdminViewer = await request.post(`${state.backendUrl}/api/auth/local/login`, {
    data: { user_id: "admin", password: "admin-pass" },
  });
  expect(loginAsAdminViewer.ok()).toBeTruthy();

  const canRead = await request.get(`${state.backendUrl}/api/projects/${projectId}`);
  expect(canRead.ok()).toBeTruthy();

  const viewerIngest = await request.post(`${state.backendUrl}/api/projects/${projectId}/vector/ingest`, {
    data: { sources: ["worldbook"] },
  });
  expect(viewerIngest.status()).toBe(403);
  const viewerIngestJson = (await viewerIngest.json()) as ApiErr;
  expect(viewerIngestJson.ok).toBe(false);
  expect(viewerIngestJson.error.code).toBe("FORBIDDEN");

  // Switch back to owner (dev_fallback) to promote to editor.
  const logout = await request.post(`${state.backendUrl}/api/auth/logout`);
  expect(logout.ok()).toBeTruthy();

  const promote = await request.put(`${state.backendUrl}/api/projects/${projectId}/memberships/admin`, {
    data: { role: "editor" },
  });
  expect(promote.ok()).toBeTruthy();

  // Editor can call editor-only routes.
  const loginAsAdminEditor = await request.post(`${state.backendUrl}/api/auth/local/login`, {
    data: { user_id: "admin", password: "admin-pass" },
  });
  expect(loginAsAdminEditor.ok()).toBeTruthy();

  const editorIngest = await request.post(`${state.backendUrl}/api/projects/${projectId}/vector/ingest`, {
    data: { sources: ["worldbook"] },
  });
  expect(editorIngest.ok()).toBeTruthy();
  const editorIngestJson = (await editorIngest.json()) as ApiOk<{ result: unknown }>;
  expect(editorIngestJson.ok).toBe(true);

  // Remove membership and verify access becomes 404 again.
  const logout2 = await request.post(`${state.backendUrl}/api/auth/logout`);
  expect(logout2.ok()).toBeTruthy();

  const remove = await request.delete(`${state.backendUrl}/api/projects/${projectId}/memberships/admin`);
  expect(remove.ok()).toBeTruthy();

  const loginAsAdminAfterRemove = await request.post(`${state.backendUrl}/api/auth/local/login`, {
    data: { user_id: "admin", password: "admin-pass" },
  });
  expect(loginAsAdminAfterRemove.ok()).toBeTruthy();

  const afterRemove = await request.get(`${state.backendUrl}/api/projects/${projectId}`);
  expect(afterRemove.status()).toBe(404);
  const afterRemoveJson = (await afterRemove.json()) as ApiErr;
  expect(afterRemoveJson.ok).toBe(false);
  expect(afterRemoveJson.error.code).toBe("NOT_FOUND");
});

test("api: project memberships forbid owner changes + validate role", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const getProject = await request.get(`${state.backendUrl}/api/projects/${projectId}`);
  expect(getProject.ok()).toBeTruthy();
  const getProjectJson = (await getProject.json()) as ApiOk<{ project: { owner_user_id: string } }>;
  const ownerUserId = getProjectJson.data.project.owner_user_id;
  expect(typeof ownerUserId).toBe("string");
  expect(ownerUserId.length).toBeGreaterThan(0);

  const addOwner = await request.post(`${state.backendUrl}/api/projects/${projectId}/memberships`, {
    data: { user_id: ownerUserId, role: "viewer" },
  });
  expect(addOwner.status()).toBe(400);
  const addOwnerJson = (await addOwner.json()) as ApiErr;
  expect(addOwnerJson.ok).toBe(false);
  expect(addOwnerJson.error.code).toBe("VALIDATION_ERROR");
  expect(addOwnerJson.error.message).toBe("不可修改 owner membership");

  const updateOwner = await request.put(`${state.backendUrl}/api/projects/${projectId}/memberships/${ownerUserId}`, {
    data: { role: "editor" },
  });
  expect(updateOwner.status()).toBe(400);
  const updateOwnerJson = (await updateOwner.json()) as ApiErr;
  expect(updateOwnerJson.ok).toBe(false);
  expect(updateOwnerJson.error.code).toBe("VALIDATION_ERROR");
  expect(updateOwnerJson.error.message).toBe("不可修改 owner membership");

  const deleteOwner = await request.delete(`${state.backendUrl}/api/projects/${projectId}/memberships/${ownerUserId}`);
  expect(deleteOwner.status()).toBe(400);
  const deleteOwnerJson = (await deleteOwner.json()) as ApiErr;
  expect(deleteOwnerJson.ok).toBe(false);
  expect(deleteOwnerJson.error.code).toBe("VALIDATION_ERROR");
  expect(deleteOwnerJson.error.message).toBe("不可移除 owner membership");

  const badRole = await request.post(`${state.backendUrl}/api/projects/${projectId}/memberships`, {
    data: { user_id: "admin", role: "owner" },
  });
  expect(badRole.status()).toBe(400);
  const badRoleJson = (await badRole.json()) as ApiErr;
  expect(badRoleJson.ok).toBe(false);
  expect(badRoleJson.error.code).toBe("VALIDATION_ERROR");
  expect(badRoleJson.error.message).toBe("role 必须为 viewer 或 editor");
});
