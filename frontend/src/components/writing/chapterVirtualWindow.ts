export const DEFAULT_ROW_HEIGHT = 48;
const DEFAULT_OVERSCAN = 6;
export const DEFAULT_VIEWPORT_HEIGHT = DEFAULT_ROW_HEIGHT * 10;

type ChapterVirtualWindowArgs = {
  itemCount: number;
  itemHeight: number;
  viewportHeight: number;
  scrollTop: number;
  overscan?: number;
};

export type ChapterVirtualWindow = {
  startIndex: number;
  endIndex: number;
  totalHeight: number;
  offsetTop: number;
};

export function getChapterVirtualWindow(args: ChapterVirtualWindowArgs): ChapterVirtualWindow {
  const itemCount = Math.max(0, Math.floor(args.itemCount));
  const itemHeight = Math.max(1, Math.floor(args.itemHeight));
  const viewportHeight = Math.max(itemHeight, Math.floor(args.viewportHeight));
  const scrollTop = Math.max(0, Math.floor(args.scrollTop));
  const overscan = Math.max(0, Math.floor(args.overscan ?? DEFAULT_OVERSCAN));

  if (itemCount === 0) {
    return {
      startIndex: 0,
      endIndex: 0,
      totalHeight: 0,
      offsetTop: 0,
    };
  }

  const maxStartIndex = Math.max(0, itemCount - 1);
  const visibleStart = Math.min(maxStartIndex, Math.max(0, Math.floor(scrollTop / itemHeight)));
  const visibleEnd = Math.min(
    itemCount,
    Math.max(visibleStart + 1, Math.ceil((scrollTop + viewportHeight) / itemHeight)),
  );
  const startIndex = Math.max(0, visibleStart - overscan);
  const endIndex = Math.min(itemCount, Math.max(visibleEnd + overscan, startIndex + 1));

  return {
    startIndex,
    endIndex,
    totalHeight: itemCount * itemHeight,
    offsetTop: startIndex * itemHeight,
  };
}

type ChapterScrollTargetArgs = {
  currentScrollTop: number;
  itemIndex: number;
  itemHeight: number;
  viewportHeight: number;
};

export function getChapterScrollTopForIndex(args: ChapterScrollTargetArgs): number | null {
  const currentScrollTop = Math.max(0, Math.floor(args.currentScrollTop));
  const itemIndex = Math.max(0, Math.floor(args.itemIndex));
  const itemHeight = Math.max(1, Math.floor(args.itemHeight));
  const viewportHeight = Math.max(itemHeight, Math.floor(args.viewportHeight));

  const itemTop = itemIndex * itemHeight;
  const itemBottom = itemTop + itemHeight;
  const viewportBottom = currentScrollTop + viewportHeight;

  if (itemTop < currentScrollTop) return itemTop;
  if (itemBottom > viewportBottom) return Math.max(0, itemBottom - viewportHeight);
  return null;
}
