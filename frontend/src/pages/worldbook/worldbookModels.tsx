import { type ReactNode } from "react";

import { containsPinyinMatch, looksLikePinyinToken, tokenizeSearch } from "../../lib/pinyin";
import type { WorldBookEntry, WorldBookPriority } from "../../services/worldbookApi";

import type { WorldBookSortMode } from "./useWorldBookFilters";

export type WorldBookEntryForm = {
  title: string;
  content_md: string;
  enabled: boolean;
  constant: boolean;
  keywords_raw: string;
  exclude_recursion: boolean;
  prevent_recursion: boolean;
  char_limit: number;
  priority: WorldBookPriority;
};

export type WorldBookFilterMeta = {
  pinyinHit: boolean;
};

export type WorldBookFilterState = {
  tokens: string[];
  metaById: Map<string, WorldBookFilterMeta>;
  entries: WorldBookEntry[];
};

export const EMPTY_WORLD_BOOK_ENTRIES: WorldBookEntry[] = [];
export const WORLD_BOOK_ENTRY_RENDER_THRESHOLD = 150;
export const WORLD_BOOK_ENTRY_PAGE_SIZE = 100;

export function taskStatusTone(status: string): "neutral" | "success" | "warning" | "danger" | "info" {
  const s = String(status || "").trim();
  if (s === "failed") return "danger";
  if (s === "running") return "warning";
  if (s === "queued") return "info";
  if (s === "done" || s === "succeeded") return "success";
  return "neutral";
}

export function highlightText(text: string, tokens: string[]): ReactNode {
  const raw = String(text ?? "");
  if (!raw) return raw;
  if (!tokens.length) return raw;

  const lower = raw.toLowerCase();
  const active = tokens
    .map((token) => String(token || "").toLowerCase())
    .filter((token) => token.length > 0 && lower.includes(token));
  if (!active.length) return raw;

  const uniq = [...new Set(active)].sort((a, b) => b.length - a.length);
  const out: ReactNode[] = [];
  let cursor = 0;

  while (cursor < raw.length) {
    let bestIdx = -1;
    let bestToken = "";
    for (const token of uniq) {
      const idx = lower.indexOf(token, cursor);
      if (idx < 0) continue;
      if (bestIdx < 0 || idx < bestIdx || (idx === bestIdx && token.length > bestToken.length)) {
        bestIdx = idx;
        bestToken = token;
      }
    }

    if (bestIdx < 0) {
      out.push(raw.slice(cursor));
      break;
    }

    if (bestIdx > cursor) out.push(raw.slice(cursor, bestIdx));
    const seg = raw.slice(bestIdx, bestIdx + bestToken.length);
    out.push(
      <mark key={`${bestIdx}:${bestToken}:${cursor}`} className="rounded bg-warning/20 px-0.5 text-ink">
        {seg}
      </mark>,
    );
    cursor = bestIdx + bestToken.length;
  }

  return <>{out}</>;
}

export function parseKeywords(raw: string): string[] {
  const tokens = raw
    .split(/[\n,，;；]/g)
    .map((value) => value.trim())
    .filter((value) => value.length > 0);
  const seen = new Set<string>();
  const out: string[] = [];
  for (const token of tokens) {
    const key = token.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(token);
  }
  return out;
}

export function joinKeywords(keywords: string[]): string {
  return (keywords ?? []).filter(Boolean).join("\n");
}

export function downloadJson(filename: string, obj: unknown) {
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function toWorldBookEntryForm(entry: WorldBookEntry | null): WorldBookEntryForm {
  return {
    title: entry?.title ?? "",
    content_md: entry?.content_md ?? "",
    enabled: entry?.enabled ?? true,
    constant: entry?.constant ?? false,
    keywords_raw: joinKeywords(entry?.keywords ?? []),
    exclude_recursion: entry?.exclude_recursion ?? false,
    prevent_recursion: entry?.prevent_recursion ?? false,
    char_limit: entry?.char_limit ?? 12000,
    priority: entry?.priority ?? "important",
  };
}

export function normalizeWorldBookCharLimit(value: number, fallback = 12000): number {
  return Number.isFinite(value) ? Math.max(0, Math.floor(value)) : fallback;
}

export function buildWorldBookFilterState(
  entries: WorldBookEntry[],
  searchText: string,
  sortMode: WorldBookSortMode,
): WorldBookFilterState {
  const tokens = tokenizeSearch(searchText);
  const priorityRank: Record<WorldBookPriority, number> = {
    must: 3,
    important: 2,
    optional: 1,
    drop_first: 0,
  };

  const metaById = new Map<string, WorldBookFilterMeta>();

  const filtered = tokens.length
    ? entries.filter((entry) => {
        const titleRaw = String(entry.title || "");
        const title = titleRaw.toLowerCase();
        const keywordsRaw = (entry.keywords ?? []).map((keyword) => String(keyword || ""));
        const keywords = keywordsRaw.map((keyword) => keyword.toLowerCase());
        const combined = `${titleRaw} ${keywordsRaw.join(" ")}`;
        let pinyinHit = false;
        const ok = tokens.every((token) => {
          if (title.includes(token)) return true;
          if (keywords.some((keyword) => keyword.includes(token))) return true;
          if (!looksLikePinyinToken(token)) return false;
          const matched = containsPinyinMatch(combined, token);
          if (!matched.matched) return false;
          pinyinHit = true;
          return true;
        });
        if (ok) metaById.set(entry.id, { pinyinHit });
        return ok;
      })
    : entries;

  const out = [...filtered];
  const byUpdatedAt = (a: WorldBookEntry, b: WorldBookEntry) => {
    const at = Date.parse(a.updated_at);
    const bt = Date.parse(b.updated_at);
    const av = Number.isFinite(at) ? at : 0;
    const bv = Number.isFinite(bt) ? bt : 0;
    return av - bv;
  };
  const byPriority = (a: WorldBookEntry, b: WorldBookEntry) => priorityRank[a.priority] - priorityRank[b.priority];
  const byEnabled = (a: WorldBookEntry, b: WorldBookEntry) => Number(Boolean(a.enabled)) - Number(Boolean(b.enabled));

  out.sort((a, b) => {
    if (sortMode === "updated_asc") return byUpdatedAt(a, b) || a.id.localeCompare(b.id);
    if (sortMode === "updated_desc") return byUpdatedAt(b, a) || a.id.localeCompare(b.id);
    if (sortMode === "priority_asc") return byPriority(a, b) || byUpdatedAt(b, a) || a.id.localeCompare(b.id);
    if (sortMode === "priority_desc") return byPriority(b, a) || byUpdatedAt(b, a) || a.id.localeCompare(b.id);
    if (sortMode === "enabled_asc") return byEnabled(a, b) || byUpdatedAt(b, a) || a.id.localeCompare(b.id);
    if (sortMode === "enabled_desc") return byEnabled(b, a) || byUpdatedAt(b, a) || a.id.localeCompare(b.id);
    return byUpdatedAt(b, a) || a.id.localeCompare(b.id);
  });

  return { tokens, metaById, entries: out };
}

export function resolveSelectedWorldBookEntryIds(options: {
  bulkSelectAllActive: boolean;
  bulkSelectedIds: string[];
  bulkExcludedIds: string[];
  filteredEntries: WorldBookEntry[];
}): string[] {
  if (!options.bulkSelectAllActive) {
    return options.bulkSelectedIds;
  }

  const excludedSet = new Set(options.bulkExcludedIds);
  return options.filteredEntries.filter((entry) => !excludedSet.has(entry.id)).map((entry) => entry.id);
}
