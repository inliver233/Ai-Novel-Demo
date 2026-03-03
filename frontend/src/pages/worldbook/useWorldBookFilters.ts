import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { worldBookFilterStorageKey } from "../../services/storageKeys";

export type WorldBookSortMode =
  | "updated_desc"
  | "updated_asc"
  | "priority_desc"
  | "priority_asc"
  | "enabled_desc"
  | "enabled_asc";

type WorldBookFilters = {
  searchText: string;
  sortMode: WorldBookSortMode;
};

const DEFAULT_WORLD_BOOK_SORT_MODE: WorldBookSortMode = "updated_desc";
const LEGACY_WORLD_BOOK_FILTER_STORAGE_KEY_PREFIX = "ainovel:worldbook:filter:";

export function parseWorldBookSortMode(value: unknown): WorldBookSortMode | null {
  const v = String(value ?? "").trim();
  if (
    v === "updated_desc" ||
    v === "updated_asc" ||
    v === "priority_desc" ||
    v === "priority_asc" ||
    v === "enabled_desc" ||
    v === "enabled_asc"
  ) {
    return v;
  }
  return null;
}

function readStoredWorldBookFilter(projectId: string): string | null {
  try {
    const nextKey = worldBookFilterStorageKey(projectId);
    const fromNext = localStorage.getItem(nextKey);
    if (fromNext !== null) return fromNext;

    const legacyKey = `${LEGACY_WORLD_BOOK_FILTER_STORAGE_KEY_PREFIX}${projectId}`;
    const fromLegacy = localStorage.getItem(legacyKey);
    if (fromLegacy === null) return null;

    localStorage.setItem(nextKey, fromLegacy);
    localStorage.removeItem(legacyKey);
    return fromLegacy;
  } catch {
    return null;
  }
}

export function resolveWorldBookFilters(options: {
  urlSearch: string | null;
  urlSort: string | null;
  storedRaw: string | null;
}): WorldBookFilters {
  let storedSearchText = "";
  let storedSortMode: WorldBookSortMode = DEFAULT_WORLD_BOOK_SORT_MODE;

  try {
    const parsed = JSON.parse(options.storedRaw || "") as { searchText?: unknown; sortMode?: unknown } | null;
    if (parsed && typeof parsed === "object") {
      if (typeof parsed.searchText === "string") storedSearchText = parsed.searchText;
      const parsedSort = parseWorldBookSortMode(parsed.sortMode);
      if (parsedSort) storedSortMode = parsedSort;
    }
  } catch {
    // ignore invalid storage payload
  }

  const nextSearchText = options.urlSearch !== null ? options.urlSearch : storedSearchText;
  const nextSortMode = parseWorldBookSortMode(options.urlSort) ?? storedSortMode;
  return { searchText: nextSearchText, sortMode: nextSortMode };
}

export function useWorldBookFilters(projectId: string | undefined) {
  const [searchParams] = useSearchParams();
  const [searchText, setSearchText] = useState("");
  const [sortMode, setSortMode] = useState<WorldBookSortMode>(DEFAULT_WORLD_BOOK_SORT_MODE);
  const urlSearch = searchParams.get("search");
  const urlSort = searchParams.get("sort");

  const initialFilters = useMemo(() => {
    if (!projectId) return { searchText: "", sortMode: DEFAULT_WORLD_BOOK_SORT_MODE };
    return resolveWorldBookFilters({
      urlSearch,
      urlSort,
      storedRaw: readStoredWorldBookFilter(projectId),
    });
  }, [projectId, urlSearch, urlSort]);

  useEffect(() => {
    setSearchText(initialFilters.searchText);
    setSortMode(initialFilters.sortMode);
  }, [initialFilters.searchText, initialFilters.sortMode]);

  useEffect(() => {
    if (!projectId) return;
    try {
      const key = worldBookFilterStorageKey(projectId);
      localStorage.setItem(
        key,
        JSON.stringify({
          searchText,
          sortMode,
        }),
      );
    } catch {
      // ignore
    }
  }, [projectId, searchText, sortMode]);

  return {
    searchText,
    setSearchText,
    sortMode,
    setSortMode,
  };
}
