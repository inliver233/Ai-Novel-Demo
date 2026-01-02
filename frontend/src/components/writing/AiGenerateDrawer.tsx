import { useEffect, type Dispatch, type SetStateAction } from "react";

import { Drawer } from "../ui/Drawer";
import type { Character, LLMPreset } from "../../types";
import type { GenerateForm } from "./types";

type Props = {
  open: boolean;
  generating: boolean;
  preset: LLMPreset | null;
  activeChapter: boolean;
  dirty: boolean;
  saving?: boolean;
  genForm: GenerateForm;
  setGenForm: Dispatch<SetStateAction<GenerateForm>>;
  characters: Character[];
  streamProgress?: { message: string; progress: number; status: string; wordCount?: number } | null;
  onClose: () => void;
  onSave: () => void | Promise<unknown>;
  onSaveAndGenerateNext?: () => void | Promise<unknown>;
  onGenerateAppend: () => void;
  onGenerateReplace: () => void;
  onCancelGenerate?: () => void;
};

export function AiGenerateDrawer(props: Props) {
  const { generating, onClose, open } = props;

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [generating, onClose, open]);

  return (
    <Drawer
      open={open}
      onClose={onClose}
      side="bottom"
      ariaLabel="AI 生成"
      panelClassName="h-[85vh] w-full overflow-y-auto rounded-atelier border-t border-border bg-canvas p-6 shadow-sm sm:h-full sm:max-w-md sm:rounded-none sm:border-l sm:border-t-0"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-content text-2xl text-ink">AI 生成</div>
          <div className="mt-1 text-xs text-subtext">
            {props.preset ? `${props.preset.provider} / ${props.preset.model}` : "未加载 LLM 配置"}
          </div>
        </div>
        <button className="btn btn-secondary" onClick={onClose} type="button">
          隐藏
        </button>
      </div>

      <div className="mt-5 grid gap-4">
        <div className="panel p-3">
          <label className="flex items-center justify-between gap-3 text-sm text-ink">
            <span>流式生成（beta）</span>
            <input
              className="checkbox"
              checked={props.genForm.stream}
              disabled={props.generating}
              name="stream"
              onChange={(e) => props.setGenForm((v) => ({ ...v, stream: e.target.checked }))}
              type="checkbox"
            />
          </label>

          <label className="mt-2 flex items-center justify-between gap-3 text-sm text-ink">
            <span>先生成规划（plan_first）</span>
            <input
              className="checkbox"
              checked={props.genForm.plan_first}
              disabled={props.generating}
              name="plan_first"
              onChange={(e) => props.setGenForm((v) => ({ ...v, plan_first: e.target.checked }))}
              type="checkbox"
            />
          </label>

          <label className="mt-2 flex items-center justify-between gap-3 text-sm text-ink">
            <span>润色（post_edit）</span>
            <input
              className="checkbox"
              checked={props.genForm.post_edit}
              disabled={props.generating}
              name="post_edit"
              onChange={(e) => props.setGenForm((v) => ({ ...v, post_edit: e.target.checked }))}
              type="checkbox"
            />
          </label>

          <label className="grid gap-1">
            <span className="text-xs text-subtext">目标字数（中文按字数=字符数）</span>
            <input
              className="input"
              disabled={props.generating}
              min={100}
              name="target_word_count"
              type="number"
              value={props.genForm.target_word_count}
              onChange={(e) => props.setGenForm((v) => ({ ...v, target_word_count: Number(e.target.value) }))}
            />
          </label>
        </div>

        {props.genForm.stream && props.generating && props.streamProgress ? (
          <div className="panel p-3">
            <div className="flex items-center justify-between gap-2 text-xs text-subtext">
              <span className="truncate">{props.streamProgress.message}</span>
              <span className="shrink-0">{props.streamProgress.progress}%</span>
            </div>
            <div className="h-2 w-full rounded bg-border">
              <div
                className="h-2 rounded bg-accent motion-safe:transition-[width] motion-safe:duration-atelier motion-safe:ease-atelier"
                style={{ width: `${Math.max(0, Math.min(100, props.streamProgress.progress))}%` }}
              />
            </div>
            {props.onCancelGenerate ? (
              <div className="flex justify-end">
                <button className="btn btn-secondary" onClick={props.onCancelGenerate} type="button">
                  取消生成
                </button>
              </div>
            ) : null}
          </div>
        ) : null}

        <label className="grid gap-1">
          <span className="text-xs text-subtext">用户指令</span>
          <textarea
            className="textarea atelier-content"
            disabled={props.generating}
            name="instruction"
            rows={5}
            value={props.genForm.instruction}
            onChange={(e) => props.setGenForm((v) => ({ ...v, instruction: e.target.value }))}
          />
        </label>

        <div className="grid gap-2">
          <div className="text-xs text-subtext">上下文注入</div>
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              checked={props.genForm.context.include_world_setting}
              disabled={props.generating}
              name="context_include_world_setting"
              onChange={(e) =>
                props.setGenForm((v) => ({ ...v, context: { ...v.context, include_world_setting: e.target.checked } }))
              }
              type="checkbox"
            />
            世界观
          </label>
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              checked={props.genForm.context.include_style_guide}
              disabled={props.generating}
              name="context_include_style_guide"
              onChange={(e) =>
                props.setGenForm((v) => ({ ...v, context: { ...v.context, include_style_guide: e.target.checked } }))
              }
              type="checkbox"
            />
            风格
          </label>
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              checked={props.genForm.context.include_constraints}
              disabled={props.generating}
              name="context_include_constraints"
              onChange={(e) =>
                props.setGenForm((v) => ({ ...v, context: { ...v.context, include_constraints: e.target.checked } }))
              }
              type="checkbox"
            />
            约束
          </label>
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              checked={props.genForm.context.include_outline}
              disabled={props.generating}
              name="context_include_outline"
              onChange={(e) =>
                props.setGenForm((v) => ({ ...v, context: { ...v.context, include_outline: e.target.checked } }))
              }
              type="checkbox"
            />
            大纲
          </label>
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              checked={props.genForm.context.include_smart_context}
              disabled={props.generating}
              name="context_include_smart_context"
              onChange={(e) =>
                props.setGenForm((v) => ({ ...v, context: { ...v.context, include_smart_context: e.target.checked } }))
              }
              type="checkbox"
            />
            智能上下文
          </label>
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              checked={props.genForm.context.require_sequential}
              disabled={props.generating}
              name="context_require_sequential"
              onChange={(e) =>
                props.setGenForm((v) => ({ ...v, context: { ...v.context, require_sequential: e.target.checked } }))
              }
              type="checkbox"
            />
            严格顺序
          </label>
        </div>

        <label className="grid gap-1">
          <span className="text-xs text-subtext">上一章注入</span>
          <select
            className="select"
            disabled={props.generating}
            name="previous_chapter"
            value={props.genForm.context.previous_chapter}
            onChange={(e) =>
              props.setGenForm((v) => ({
                ...v,
                context: {
                  ...v.context,
                  previous_chapter: e.target.value as GenerateForm["context"]["previous_chapter"],
                },
              }))
            }
          >
            <option value="none">不注入</option>
            <option value="tail">结尾（推荐）</option>
            <option value="summary">摘要</option>
            <option value="content">正文</option>
          </select>
          <div className="text-[11px] text-subtext">结尾更利于强衔接，减少开头复述。</div>
        </label>

        <div className="grid gap-2">
          <div className="text-xs text-subtext">注入角色（可选）</div>
          {props.characters.length === 0 ? <div className="text-sm text-subtext">暂无角色</div> : null}
          <div className="max-h-40 overflow-auto rounded-atelier border border-border bg-surface p-2">
            {props.characters.map((c) => (
              <label key={c.id} className="flex items-center gap-2 px-2 py-1 text-sm text-ink">
                <input
                  className="checkbox"
                  checked={props.genForm.context.character_ids.includes(c.id)}
                  disabled={props.generating}
                  name={`character_${c.id}`}
                  onChange={(e) => {
                    props.setGenForm((v) => {
                      const next = new Set(v.context.character_ids);
                      if (e.target.checked) next.add(c.id);
                      else next.delete(c.id);
                      return { ...v, context: { ...v.context, character_ids: Array.from(next) } };
                    });
                  }}
                  type="checkbox"
                />
                <span className="truncate">{c.name}</span>
              </label>
            ))}
          </div>
        </div>

        <div className="panel p-3 text-xs text-subtext">
          生成结果不会自动保存到数据库，请生成后点击“保存”（或 Ctrl/Cmd+S）。
        </div>
      </div>

      <div className="mt-5 flex flex-wrap justify-end gap-2">
        <button
          className="btn btn-primary"
          disabled={props.generating || !props.activeChapter}
          onClick={props.onGenerateReplace}
          type="button"
        >
          {props.generating ? "生成中..." : "生成"}
        </button>
        {props.onSaveAndGenerateNext ? (
          <button
            className="btn btn-primary"
            disabled={props.generating || props.saving || !props.activeChapter}
            onClick={() => void props.onSaveAndGenerateNext?.()}
            type="button"
          >
            保存并继续
          </button>
        ) : null}
        <button
          className="btn btn-secondary"
          disabled={props.generating || !props.activeChapter}
          onClick={props.onGenerateAppend}
          type="button"
        >
          {props.generating ? "生成中..." : "追加生成"}
        </button>
        <button
          className="btn btn-secondary"
          disabled={props.generating || props.saving || !props.activeChapter || !props.dirty}
          onClick={() => void props.onSave()}
          type="button"
        >
          保存
        </button>
      </div>
    </Drawer>
  );
}
