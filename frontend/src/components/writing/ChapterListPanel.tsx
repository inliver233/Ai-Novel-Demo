import type { ChapterListItem } from "../../types";

import { ChapterVirtualList } from "./ChapterVirtualList";

export function ChapterListPanel(props: {
  chapters: ChapterListItem[];
  activeId: string | null;
  onSelectChapter: (chapterId: string) => void;
  containerClassName?: string;
}) {
  const containerClassName =
    props.containerClassName ?? "panel flex h-[calc(100vh-220px)] min-h-[480px] flex-col overflow-hidden p-2";

  return (
    <div className={containerClassName}>
      <ChapterVirtualList
        chapters={props.chapters}
        activeId={props.activeId}
        onSelectChapter={props.onSelectChapter}
        variant="panel"
      />
    </div>
  );
}
