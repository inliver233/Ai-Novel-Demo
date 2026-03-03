import { useCallback, useEffect, useMemo, useState } from "react";
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
  const urlSearch = searchParams.get("search");
  const urlSort = searchParams.get("sort");
  const stateToken = `${projectId ?? "none"}::${urlSearch ?? ""}::${urlSort ?? ""}`;

  const initialFilters = useMemo(() => {
    if (!projectId) return { searchText: "", sortMode: DEFAULT_WORLD_BOOK_SORT_MODE };
    return resolveWorldBookFilters({
      urlSearch,
      urlSort,
      storedRaw: readStoredWorldBookFilter(projectId),
    });
  }, [projectId, urlSearch, urlSort]);

  const [state, setState] = useState(() => ({
    token: stateToken,
    searchText: initialFilters.searchText,
    sortMode: initialFilters.sortMode,
  }));

  const effective =
    state.token === stateToken
      ? state
      : {
          token: stateToken,
          searchText: initialFilters.searchText,
          sortMode: initialFilters.sortMode,
        };

  const setSearchText = useCallback(
    (next: string | ((prev: string) => string)) => {
      setState((prev) => {
        const base =
          prev.token === stateToken
            ? prev
            : {
                token: stateToken,
                searchText: initialFilters.searchText,
                sortMode: initialFilters.sortMode,
              };
        const value = typeof next === "function" ? next(base.searchText) : next;
        return { ...base, searchText: value };
      });
    },
    [initialFilters.searchText, initialFilters.sortMode, stateToken],
  );

  const setSortMode = useCallback(
    (next: WorldBookSortMode | ((prev: WorldBookSortMode) => WorldBookSortMode)) => {
      setState((prev) => {
        const base =
          prev.token === stateToken
            ? prev
            : {
                token: stateToken,
                searchText: initialFilters.searchText,
                sortMode: initialFilters.sortMode,
              };
        const value = typeof next === "function" ? next(base.sortMode) : next;
        return { ...base, sortMode: value };
      });
    },
    [initialFilters.searchText, initialFilters.sortMode, stateToken],
  );

  useEffect(() => {
    if (!projectId) return;
    try {
      const key = worldBookFilterStorageKey(projectId);
      localStorage.setItem(
        key,
        JSON.stringify({
          searchText: effective.searchText,
          sortMode: effective.sortMode,
        }),
      );
    } catch {
      // ignore
    }
  }, [effective.searchText, effective.sortMode, projectId]);

  return {
    searchText: effective.searchText,
    setSearchText,
    sortMode: effective.sortMode,
    setSortMode,
  };
}
