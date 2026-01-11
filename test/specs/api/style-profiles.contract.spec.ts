import { test, expect } from "@playwright/test";

import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };
type ApiErr = { ok: false; error: { code: string; message: string; details?: unknown }; request_id: string };

test("api: writing_styles rejects prompt_content too long", async ({ request }) => {
  const state = loadState();

  const tooLong = "a".repeat(9000);
  const res = await request.post(`${state.backendUrl}/api/writing_styles`, {
    data: { name: "too-long-style", description: "for test", prompt_content: tooLong },
  });

  expect(res.status()).toBe(400);
  const json = (await res.json()) as ApiErr;
  expect(json.ok).toBe(false);
  expect(json.error.code).toBe("VALIDATION_ERROR");
});

test("api: cannot set project default to another user's style", async ({ request }) => {
  const state = loadState();

  // Create a non-preset style as the dev fallback user (no session cookie).
  const styleRes = await request.post(`${state.backendUrl}/api/writing_styles`, {
    data: { name: "Other User Style", description: "for test", prompt_content: "prompt" },
  });
  expect(styleRes.ok()).toBeTruthy();
  const styleJson = (await styleRes.json()) as ApiOk<{ style: { id: string } }>;
  const otherStyleId = styleJson.data.style.id;

  // Login as admin and create a project owned by admin.
  const login = await request.post(`${state.backendUrl}/api/auth/local/login`, {
    data: { user_id: "admin", password: "admin-pass" },
  });
  expect(login.ok()).toBeTruthy();

  const projectRes = await request.post(`${state.backendUrl}/api/projects`, {
    data: { name: "Admin Project", genre: "Test", logline: "for test" },
  });
  expect(projectRes.ok()).toBeTruthy();
  const projectJson = (await projectRes.json()) as ApiOk<{ project: { id: string } }>;
  const projectId = projectJson.data.project.id;

  const res = await request.put(`${state.backendUrl}/api/projects/${projectId}/writing_style_default`, {
    data: { style_id: otherStyleId },
  });
  expect(res.status()).toBe(403);

  const json = (await res.json()) as ApiErr;
  expect(json.ok).toBe(false);
  expect(json.error.code).toBe("FORBIDDEN");
});

