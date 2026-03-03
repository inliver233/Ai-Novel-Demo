import { useCallback, useMemo, useState } from "react";

type UseWorldBookPaginationOptions = {
  threshold: number;
  pageSize: number;
  resetToken: string;
};

export function useWorldBookPagination<T>(items: T[], options: UseWorldBookPaginationOptions) {
  const [pageState, setPageState] = useState(() => ({ token: options.resetToken, pageIndex: 0 }));
  const rawPageIndex = pageState.token === options.resetToken ? pageState.pageIndex : 0;
  const paginate = items.length > options.threshold;
  const totalPages = paginate ? Math.ceil(items.length / options.pageSize) : 1;
  const maxPageIndex = Math.max(0, totalPages - 1);
  const pageIndexClamped = Math.min(rawPageIndex, maxPageIndex);
  const pageStart = paginate ? pageIndexClamped * options.pageSize : 0;
  const pageEnd = paginate ? Math.min(pageStart + options.pageSize, items.length) : items.length;

  const setPageIndex = useCallback(
    (next: number | ((prev: number) => number)) => {
      setPageState((prev) => {
        const base = prev.token === options.resetToken ? prev.pageIndex : 0;
        const resolved = typeof next === "function" ? next(base) : next;
        const normalized = Number.isFinite(resolved) ? Math.max(0, Math.floor(resolved)) : 0;
        return { token: options.resetToken, pageIndex: normalized };
      });
    },
    [options.resetToken],
  );

  const pageItems = useMemo(
    () => (paginate ? items.slice(pageStart, pageEnd) : items),
    [items, pageEnd, pageStart, paginate],
  );

  return {
    paginate,
    totalPages,
    pageIndex: pageIndexClamped,
    pageStart,
    pageEnd,
    pageItems,
    setPageIndex,
  };
}
