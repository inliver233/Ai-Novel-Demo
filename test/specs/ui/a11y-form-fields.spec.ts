import { type Page } from "@playwright/test";
import { test, expect, waitForWorldbookPageReady } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

type MissingFieldSummary = {
  tag: string;
  type?: string;
  id?: string;
  name?: string;
  ariaLabel?: string;
  placeholder?: string;
  className?: string;
};

async function expandDetailsByTitle(page: Page, title: string) {
  const summary = page.locator("summary", { hasText: title });
  await expect(summary).toBeVisible();
  const details = summary.locator("..");
  if ((await details.getAttribute("open")) === null) {
    await summary.click();
    await expect(details).toHaveAttribute("open", "");
  }
}

async function collectMissingFormFields(page: Page): Promise<MissingFieldSummary[]> {
  return await page.evaluate(() => {
    const isVisible = (el: Element): boolean => {
      if (!(el instanceof HTMLElement)) return false;
      if (el.closest("[hidden]")) return false;
      if (el.closest('[aria-hidden=\"true\"]')) return false;
      const style = window.getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") return false;
      const rect = el.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return false;
      return true;
    };

    const safeText = (value: string | null): string | undefined => {
      if (!value) return undefined;
      const trimmed = value.trim();
      if (!trimmed) return undefined;
      return trimmed.length > 120 ? `${trimmed.slice(0, 117)}...` : trimmed;
    };

    const missing: MissingFieldSummary[] = [];

    const root = document.querySelector("main") ?? document;

    for (const el of Array.from(root.querySelectorAll("input, select, textarea"))) {
      if (!isVisible(el)) continue;

      if (el instanceof HTMLInputElement) {
        const type = (el.getAttribute("type") || "text").toLowerCase();
        if (["hidden", "submit", "button", "reset", "image"].includes(type)) continue;
      }

      const id = (el.getAttribute("id") || "").trim();
      const name = (el.getAttribute("name") || "").trim();
      if (id || name) continue;

      const ariaLabel = safeText(el.getAttribute("aria-label"));
      if (!ariaLabel) continue;

      const summary: MissingFieldSummary = {
        tag: el.tagName.toLowerCase(),
        type: el instanceof HTMLInputElement ? (el.getAttribute("type") || "text") : undefined,
        id: id || undefined,
        name: name || undefined,
        ariaLabel,
        placeholder: el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement ? safeText(el.placeholder) : undefined,
        className: safeText(el.getAttribute("class")),
      };

      missing.push(summary);
      if (missing.length >= 40) break;
    }

    return missing;
  });
}

function formatMissing(missing: MissingFieldSummary[]): string {
  if (!missing.length) return "";
  return missing
    .map((m) => {
      const parts = [
        `tag=${m.tag}`,
        m.type ? `type=${m.type}` : null,
        m.ariaLabel ? `aria-label=${m.ariaLabel}` : null,
        m.placeholder ? `placeholder=${m.placeholder}` : null,
        m.className ? `class=${m.className}` : null,
      ].filter(Boolean);
      return `- ${parts.join(" | ")}`;
    })
    .join("\n");
}

test("ui: a11y form fields have id or name (key pages)", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  const check = async (label: string) => {
    const missing = await collectMissingFormFields(page);
    expect(
      missing,
      `Missing id/name form fields on ${label}:\n${formatMissing(missing) || "(none)"}`,
    ).toEqual([]);
  };

  await page.goto(`/projects/${projectId}/settings`);
  await expect(page.getByText("项目信息", { exact: true })).toBeVisible();
  await expandDetailsByTitle(page, "向量检索（Vector RAG）");
  await expandDetailsByTitle(page, "Rerank 提供方配置");
  await check("SettingsPage");

  await page.goto(`/projects/${projectId}/prompts#rag-config`);
  await expect(page.getByRole("heading", { name: "模型配置", exact: true })).toBeVisible();
  await check("PromptsPage");

  await page.goto(`/projects/${projectId}/search`);
  await expect(page.getByLabel("search_query", { exact: true })).toBeVisible();
  await check("SearchPage");

  await page.goto(`/projects/${projectId}/writing`);
  await expect(page.getByText("请选择或新建章节开始写作。", { exact: true })).toBeVisible();
  await check("WritingPage");

  await page.goto(`/projects/${projectId}/worldbook`);
  await waitForWorldbookPageReady(page);
  await check("WorldBookPage");
});
