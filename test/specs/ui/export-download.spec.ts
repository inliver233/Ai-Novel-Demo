import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

test("ui: export markdown triggers download", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  await page.goto(`/projects/${projectId}/export`);
  await expect(page.getByRole("button", { name: "导出 Markdown", exact: true })).toBeVisible();

  await page.evaluate(() => {
    // @ts-ignore
    window.__e2eDownloads = [];
    const orig = HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click = function clickPatched() {
      try {
        // @ts-ignore
        window.__e2eDownloads.push({ href: this.href, download: this.download });
      } catch {
        // ignore
      }
      // @ts-ignore
      return orig.apply(this, arguments);
    };
  });

  const exportResp = page.waitForResponse((resp) => {
    return resp.request().method() === "GET" && resp.url().includes(`/api/projects/${projectId}/export/markdown`);
  });

  await page.getByRole("button", { name: "导出 Markdown", exact: true }).click();

  const resp = await exportResp;
  expect(resp.ok()).toBeTruthy();
  const headers = resp.headers();
  expect(headers["content-type"] ?? "").toContain("text/markdown");
  expect(headers["content-disposition"] ?? "").toContain("attachment");

  const downloads = (await page.evaluate(() => {
    // @ts-ignore
    return window.__e2eDownloads || [];
  })) as Array<{ href?: string; download?: string }>;

  expect(downloads.length).toBeGreaterThan(0);
  expect(downloads[0]?.download ?? "").toMatch(/\.md$/);
  expect(downloads[0]?.href ?? "").toMatch(/^blob:/);
});
