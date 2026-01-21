import { List } from "lucide-react";

import { UI_COPY } from "../../lib/uiCopy";
import type { OutlineListItem } from "../../types";

export function WritingToolbar(props: {
  outlines: OutlineListItem[];
  activeOutlineId: string;
  chaptersCount: number;
  batchProgressText: string;
  aiGenerateDisabled: boolean;
  onSwitchOutline: (outlineId: string) => void;
  onOpenChapterList: () => void;
  onOpenBatch: () => void;
  onOpenHistory: () => void;
  onOpenAiGenerate: () => void;
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
          <button className="btn btn-primary" onClick={props.onCreateChapter} type="button">
            新增章节
          </button>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
        <div className="grid gap-1">
          <div className="text-[11px] text-subtext">基础写作</div>
          <div className="flex flex-wrap items-center gap-2">
            <button className="btn btn-secondary" disabled={props.aiGenerateDisabled} onClick={props.onOpenAiGenerate} type="button">
              AI 生成
            </button>
            <button className="btn btn-secondary" onClick={props.onOpenBatch} type="button">
              批量生成{props.batchProgressText}
            </button>
            <button className="btn btn-secondary" onClick={props.onOpenHistory} type="button">
              生成记录
            </button>
            <button className="btn btn-secondary" onClick={props.onOpenForeshadow} type="button">
              伏笔面板
            </button>
          </div>
        </div>

        <div className="grid gap-1">
          <div className="text-[11px] text-subtext">高级调试</div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              className="btn btn-secondary"
              aria-label="Memory Update"
              onClick={props.onOpenMemoryUpdate}
              type="button"
            >
              记忆更新（Memory Update）
            </button>
            <button className="btn btn-secondary" onClick={props.onOpenContextPreview} type="button">
              {UI_COPY.writing.contextPreview}
            </button>
            <button className="btn btn-secondary" onClick={props.onOpenTaskCenter} type="button">
              任务中心
            </button>
          </div>
        </div>
      </div>

      <div className="mt-3 text-xs text-subtext">
        基础写作：生成草稿、批量生成、回看生成记录、管理伏笔。高级调试：查看上下文注入、批量写入记忆、追踪后台任务。
      </div>
    </div>
  );
}
