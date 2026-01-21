import { List } from "lucide-react";

import { UI_COPY } from "../../lib/uiCopy";
import type { OutlineListItem } from "../../types";

export function WritingToolbar(props: {
  outlines: OutlineListItem[];
  activeOutlineId: string;
  chaptersCount: number;
  batchProgressText: string;
  onSwitchOutline: (outlineId: string) => void;
  onOpenChapterList: () => void;
  onOpenBatch: () => void;
  onOpenHistory: () => void;
  onOpenContextPreview: () => void;
  onOpenMemoryUpdate: () => void;
  onOpenTaskCenter: () => void;
  onOpenForeshadow: () => void;
  onCreateChapter: () => void;
}) {
  return (
    <div className="panel p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-subtext">当前大纲</span>
          <select
            className="select w-auto"
            name="active_outline_id"
            value={props.activeOutlineId}
            onChange={(e) => props.onSwitchOutline(e.target.value)}
          >
            {props.outlines.map((o) => (
              <option key={o.id} value={o.id}>
                {o.title}
                {o.has_chapters ? "（已有章节）" : ""}
              </option>
            ))}
          </select>
          <span className="text-xs text-subtext">共 {props.chaptersCount} 章</span>
        </div>

        <div className="flex items-center gap-2">
          <button className="btn btn-secondary lg:hidden" onClick={props.onOpenChapterList} type="button">
            <List size={16} />
            章节列表
          </button>
          <button className="btn btn-secondary" onClick={props.onOpenBatch} type="button">
            批量生成{props.batchProgressText}
          </button>
          <button className="btn btn-secondary" onClick={props.onOpenHistory} type="button">
            生成记录
          </button>
          <button className="btn btn-secondary" aria-label="Memory Update" onClick={props.onOpenMemoryUpdate} type="button">
            记忆更新（Memory Update）
          </button>
          <button className="btn btn-secondary" onClick={props.onOpenTaskCenter} type="button">
            任务中心
          </button>
          <button className="btn btn-secondary" onClick={props.onOpenForeshadow} type="button">
            伏笔面板
          </button>
          <button className="btn btn-secondary" onClick={props.onOpenContextPreview} type="button">
            {UI_COPY.writing.contextPreview}
          </button>
          <button className="btn btn-primary" onClick={props.onCreateChapter} type="button">
            新增章节
          </button>
        </div>
      </div>
    </div>
  );
}
