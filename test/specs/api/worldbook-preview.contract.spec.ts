import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

type ApiOk<T> = { ok: true; data: T; request_id: string };

test("api: worldbook preview_trigger contract + memory/retrieve includes reasons", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  const constantRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries`, {
    data: {
      title: "E2E WB Constant",
      content_md: "dragon",
      enabled: true,
      constant: true,
      keywords: [],
      exclude_recursion: false,
      prevent_recursion: false,
      char_limit: 12000,
      priority: "important",
    },
  });
  expect(constantRes.ok()).toBeTruthy();

  const keywordRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries`, {
    data: {
      title: "E2E WB Keyword",
      content_md: "E2E_KEYWORD_CONTENT",
      enabled: true,
      constant: false,
      keywords: ["dragon"],
      exclude_recursion: false,
      prevent_recursion: false,
      char_limit: 12000,
      priority: "important",
    },
  });
  expect(keywordRes.ok()).toBeTruthy();

  const previewRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries/preview_trigger`, {
    data: {
      query_text: "dragon",
      include_constant: true,
      enable_recursion: true,
      char_limit: 10,
    },
  });
  expect(previewRes.ok()).toBeTruthy();

  const previewJson = (await previewRes.json()) as ApiOk<{
    triggered: Array<{ id: string; title: string; reason: string; priority: string }>;
    text_md: string;
    truncated: boolean;
    match_config?: { alias_enabled?: boolean };
  }>;
  expect(previewJson.ok).toBe(true);
  expect(typeof previewJson.request_id).toBe("string");
  expect(previewJson.request_id.length).toBeGreaterThan(0);

  expect(Array.isArray(previewJson.data.triggered)).toBe(true);
  expect(typeof previewJson.data.text_md).toBe("string");
  expect(typeof previewJson.data.truncated).toBe("boolean");
  for (const item of previewJson.data.triggered) {
    expect(typeof item.id).toBe("string");
    expect(item.id.length).toBeGreaterThan(0);
    expect(typeof item.title).toBe("string");
    expect(typeof item.reason).toBe("string");
    expect(typeof item.priority).toBe("string");
  }
  expect(previewJson.data.triggered.some((t) => t.reason === "constant")).toBe(true);
  expect(previewJson.data.triggered.some((t) => t.reason.includes("keyword:dragon"))).toBe(true);

  // Minimal enhanced matching coverage: alias match (enabled in test/global-setup.ts).
  expect(Boolean(previewJson.data.match_config?.alias_enabled)).toBe(true);

  const aliasRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries`, {
    data: {
      title: "E2E WB Alias",
      content_md: "E2E_ALIAS_CONTENT",
      enabled: true,
      constant: false,
      keywords: ["alias:drake"],
      exclude_recursion: false,
      prevent_recursion: false,
      char_limit: 12000,
      priority: "important",
    },
  });
  expect(aliasRes.ok()).toBeTruthy();

  const aliasPreviewRes = await request.post(`${state.backendUrl}/api/projects/${projectId}/worldbook_entries/preview_trigger`, {
    data: {
      query_text: "drake",
      include_constant: false,
      enable_recursion: true,
      char_limit: 2000,
    },
  });
  expect(aliasPreviewRes.ok()).toBeTruthy();
  const aliasPreviewJson = (await aliasPreviewRes.json()) as ApiOk<{
    triggered: Array<{ id: string; title: string; reason: string; priority: string }>;
    match_config?: { alias_enabled?: boolean };
  }>;
  expect(Boolean(aliasPreviewJson.data.match_config?.alias_enabled)).toBe(true);
  expect(aliasPreviewJson.data.triggered.some((t) => t.reason === "alias:drake")).toBe(true);

  const retrieveRes = await request.get(`${state.backendUrl}/api/projects/${projectId}/memory/retrieve`);
  expect(retrieveRes.ok()).toBeTruthy();
  const retrieveJson = (await retrieveRes.json()) as ApiOk<{ worldbook: Record<string, unknown> }>;
  expect(retrieveJson.ok).toBe(true);

  const worldbook = retrieveJson.data.worldbook as { triggered?: unknown[] };
  expect(Array.isArray(worldbook.triggered)).toBe(true);
  const triggered = worldbook.triggered as Array<Record<string, unknown>>;
  expect(triggered.some((t) => String(t.reason ?? "") === "constant")).toBe(true);
  expect(triggered.some((t) => String(t.reason ?? "").includes("keyword:dragon"))).toBe(true);

  // Must not leak api keys or secrets (bootstrapProject uses "test-key").
  const raw = JSON.stringify({ previewJson, aliasPreviewJson, retrieveJson });
  expect(raw).not.toContain("test-key");
  expect(raw).not.toMatch(/sk-[a-zA-Z0-9]{10,}/);
});
