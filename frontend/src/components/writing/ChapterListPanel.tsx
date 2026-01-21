import { humanizeChapterStatus } from "../../lib/humanize";
import type { Chapter } from "../../types";

export function ChapterListPanel(props: {
  chapters: Chapter[];
  activeId: string | null;
  onSelectChapter: (chapterId: string) => void;
  containerClassName?: string;
}) {
  const containerClassName = props.containerClassName ?? "panel p-2";
  return (
    <div className={containerClassName}>
      {props.chapters.length === 0 ? (
        <div className="p-3 text-sm text-subtext">还没有章节，先新建一个吧。</div>
      ) : (
        <div className="flex flex-col gap-1">
          {props.chapters.map((c) => (
            <button
              key={c.id}
              className={
                c.id === props.activeId
                  ? "ui-focus-ring ui-transition-fast rounded-atelier bg-canvas px-3 py-2 text-left text-sm text-ink"
                  : "ui-focus-ring ui-transition-fast rounded-atelier px-3 py-2 text-left text-sm text-subtext hover:bg-canvas hover:text-ink"
              }
              onClick={() => props.onSelectChapter(c.id)}
              type="button"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0 truncate">
                  <span className="mr-2 text-xs text-subtext">#{c.number}</span>
                  <span className="truncate">{c.title ?? "未命名章节"}</span>
                </div>
                <span className="shrink-0 text-[11px] text-subtext">{humanizeChapterStatus(c.status)}</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
