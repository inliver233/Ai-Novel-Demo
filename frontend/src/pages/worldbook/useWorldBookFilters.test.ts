import { describe, expect, it } from "vitest";

import { parseWorldBookSortMode, resolveWorldBookFilters } from "./useWorldBookFilters";

describe("useWorldBookFilters helpers", () => {
  it("parses valid sort modes and rejects invalid values", () => {
    expect(parseWorldBookSortMode("updated_desc")).toBe("updated_desc");
    expect(parseWorldBookSortMode("priority_asc")).toBe("priority_asc");
    expect(parseWorldBookSortMode("invalid")).toBeNull();
  });

  it("prefers URL search/sort over storage payload", () => {
    const resolved = resolveWorldBookFilters({
      urlSearch: "dragon",
      urlSort: "enabled_asc",
      storedRaw: JSON.stringify({ searchText: "legacy", sortMode: "updated_desc" }),
    });

    expect(resolved).toEqual({ searchText: "dragon", sortMode: "enabled_asc" });
  });

  it("falls back to storage/default when URL values are missing or invalid", () => {
    const fromStorage = resolveWorldBookFilters({
      urlSearch: null,
      urlSort: "bad_sort",
      storedRaw: JSON.stringify({ searchText: "city", sortMode: "priority_desc" }),
    });
    expect(fromStorage).toEqual({ searchText: "city", sortMode: "priority_desc" });

    const fromDefault = resolveWorldBookFilters({
      urlSearch: null,
      urlSort: null,
      storedRaw: "not-json",
    });
    expect(fromDefault).toEqual({ searchText: "", sortMode: "updated_desc" });
  });
});
