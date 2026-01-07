import { test, expect } from "@playwright/test";

import { bootstrapProject } from "../../lib/bootstrap";
import { loadState } from "../../lib/state";

test("api: export markdown contract (filters + headers)", async ({ request }) => {
  const state = loadState();
  const { projectId } = await bootstrapProject(request);

  // Make filename/header assertions meaningful for non-ascii names.
  const renamed = await request.put(`${state.backendUrl}/api/projects/${projectId}`, { data: { name: "E2E 项目" } });
  expect(renamed.ok()).toBeTruthy();

  const putSettings = await request.put(`${state.backendUrl}/api/projects/${projectId}/settings`, {
    data: { world_setting: "E2E world", style_guide: "E2E style", constraints: "E2E constraints" },
  });
  expect(putSettings.ok()).toBeTruthy();

  const createChar = await request.post(`${state.backendUrl}/api/projects/${projectId}/characters`, {
    data: { name: "Alice", role: "Protagonist", profile: "Brave", notes: "E2E character" },
  });
  expect(createChar.ok()).toBeTruthy();

  const bulk = await request.post(`${state.backendUrl}/api/projects/${projectId}/chapters/bulk_create`, {
    data: { chapters: [{ number: 1, title: "第一章", plan: "" }, { number: 2, title: "第二章", plan: "" }] },
  });
  expect(bulk.ok()).toBeTruthy();
  const bulkJson = (await bulk.json()) as { ok: boolean; data: { chapters: Array<{ id: string; number: number }> } };
  const c1 = bulkJson.data.chapters.find((c) => c.number === 1)?.id;
  const c2 = bulkJson.data.chapters.find((c) => c.number === 2)?.id;
  expect(c1).toBeTruthy();
  expect(c2).toBeTruthy();

  const seed1 = await request.put(`${state.backendUrl}/api/chapters/${c1}`, { data: { content_md: "DONE content", status: "done" } });
  const seed2 = await request.put(`${state.backendUrl}/api/chapters/${c2}`, {
    data: { content_md: "DRAFT content", status: "drafting" },
  });
  expect(seed1.ok()).toBeTruthy();
  expect(seed2.ok()).toBeTruthy();

  const all = await request.get(`${state.backendUrl}/api/projects/${projectId}/export/markdown`);
  expect(all.ok()).toBeTruthy();
  const allHeaders = all.headers();
  expect(allHeaders["content-type"] ?? "").toContain("text/markdown");
  const cd = allHeaders["content-disposition"] ?? "";
  expect(cd).toContain("attachment");
  expect(cd).toContain("filename=");
  expect(cd).toContain(".md");
  expect(cd).toContain("filename*=");
  const allText = await all.text();
  expect(allText).toContain("## 设定");
  expect(allText).toContain("## 角色卡");
  expect(allText).toContain("## 大纲");
  expect(allText).toContain("## 正文");
  expect(allText).toContain("### 第1章");
  expect(allText).toContain("### 第2章");

  const doneOnly = await request.get(`${state.backendUrl}/api/projects/${projectId}/export/markdown?chapters=done`);
  expect(doneOnly.ok()).toBeTruthy();
  const doneText = await doneOnly.text();
  expect(doneText).toContain("### 第1章");
  expect(doneText).not.toContain("### 第2章");

  const minimal = await request.get(
    `${state.backendUrl}/api/projects/${projectId}/export/markdown?include_settings=0&include_characters=0&include_outline=0`,
  );
  expect(minimal.ok()).toBeTruthy();
  const minimalText = await minimal.text();
  expect(minimalText).not.toContain("## 设定");
  expect(minimalText).not.toContain("## 角色卡");
  expect(minimalText).not.toContain("## 大纲");
  expect(minimalText).toContain("## 正文");
});
