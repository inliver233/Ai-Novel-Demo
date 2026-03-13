import { describe, expect, it } from "vitest";

import type { WorldBookEntry } from "../../services/worldbookApi";

import {
  buildWorldBookFilterState,
  normalizeWorldBookCharLimit,
  parseKeywords,
  resolveSelectedWorldBookEntryIds,
  toWorldBookEntryForm,
} from "./worldbookModels";

function makeEntry(overrides: Partial<WorldBookEntry>): WorldBookEntry {
  return {
    id: overrides.id ?? "entry-1",
    project_id: overrides.project_id ?? "project-1",
    title: overrides.title ?? "Alpha",
    content_md: overrides.content_md ?? "content",
    enabled: overrides.enabled ?? true,
    constant: overrides.constant ?? false,
    keywords: overrides.keywords ?? [],
    exclude_recursion: overrides.exclude_recursion ?? false,
    prevent_recursion: overrides.prevent_recursion ?? false,
    char_limit: overrides.char_limit ?? 12000,
    priority: overrides.priority ?? "important",
    updated_at: overrides.updated_at ?? "2026-03-13T00:00:00Z",
  };
}

describe("worldbookModels", () => {
  it("deduplicates keywords case-insensitively and trims separators", () => {
    expect(parseKeywords("dragon\nDragon, 城堡；castle ; dragon")).toEqual(["dragon", "城堡", "castle"]);
  });

  it("builds filter state with keyword search and sort order", () => {
    const entries = [
      makeEntry({
        id: "1",
        title: "Alpha",
        keywords: ["city"],
        priority: "optional",
        updated_at: "2026-03-11T00:00:00Z",
      }),
      makeEntry({
        id: "2",
        title: "Beta",
        keywords: ["dragon"],
        priority: "must",
        enabled: false,
        updated_at: "2026-03-12T00:00:00Z",
      }),
      makeEntry({
        id: "3",
        title: "Gamma",
        keywords: ["dragon"],
        priority: "important",
        enabled: true,
        updated_at: "2026-03-13T00:00:00Z",
      }),
    ];

    const filtered = buildWorldBookFilterState(entries, "dragon", "enabled_desc");

    expect(filtered.entries.map((entry) => entry.id)).toEqual(["3", "2"]);
    expect(filtered.tokens).toEqual(["dragon"]);
  });

  it("resolves selected ids for explicit and select-all bulk mode", () => {
    const entries = [makeEntry({ id: "1" }), makeEntry({ id: "2" }), makeEntry({ id: "3" })];

    expect(
      resolveSelectedWorldBookEntryIds({
        bulkSelectAllActive: false,
        bulkSelectedIds: ["2"],
        bulkExcludedIds: [],
        filteredEntries: entries,
      }),
    ).toEqual(["2"]);

    expect(
      resolveSelectedWorldBookEntryIds({
        bulkSelectAllActive: true,
        bulkSelectedIds: [],
        bulkExcludedIds: ["2"],
        filteredEntries: entries,
      }),
    ).toEqual(["1", "3"]);
  });

  it("maps entry data into editable form defaults", () => {
    const entry = makeEntry({
      title: "Dragon",
      keywords: ["dragon", "castle"],
      constant: true,
      char_limit: 321,
      priority: "must",
    });

    expect(toWorldBookEntryForm(entry)).toMatchObject({
      title: "Dragon",
      keywords_raw: "dragon\ncastle",
      constant: true,
      char_limit: 321,
      priority: "must",
    });
    expect(toWorldBookEntryForm(null).enabled).toBe(true);
  });

  it("normalizes char limits to non-negative integers", () => {
    expect(normalizeWorldBookCharLimit(123.9)).toBe(123);
    expect(normalizeWorldBookCharLimit(-4)).toBe(0);
    expect(normalizeWorldBookCharLimit(Number.NaN)).toBe(12000);
  });
});
