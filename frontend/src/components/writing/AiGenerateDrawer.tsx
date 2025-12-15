import type { Dispatch, SetStateAction } from "react";

import type { Character, LLMPreset } from "../../types";
import type { GenerateForm } from "./types";

type Props = {
  open: boolean;
  generating: boolean;
  preset: LLMPreset | null;
  activeChapter: boolean;
  genForm: GenerateForm;
  setGenForm: Dispatch<SetStateAction<GenerateForm>>;
  characters: Character[];
  onClose: () => void;
  onGenerateAppend: () => void;
  onGenerateReplace: () => void;
};

export function AiGenerateDrawer(props: Props) {
  if (!props.open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30">
      <div className="h-full w-full max-w-md border-l border-border bg-canvas p-6">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="font-content text-2xl text-ink">AI 生成</div>
            <div className="mt-1 text-xs text-subtext">
              {props.preset ? `${props.preset.provider} / ${props.preset.model}` : "未加载 LLM 配置"}
            </div>
          </div>
          <button
            className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink hover:bg-canvas disabled:opacity-60"
            disabled={props.generating}
            onClick={props.onClose}
            type="button"
          >
            关闭
          </button>
        </div>

        <div className="mt-5 grid gap-4">
          <label className="grid gap-1">
            <span className="text-xs text-subtext">用户指令</span>
            <textarea
              className="atelier-content w-full rounded-atelier border border-border bg-surface px-3 py-3 text-ink outline-none disabled:opacity-60"
              disabled={props.generating}
              rows={5}
              value={props.genForm.instruction}
              onChange={(e) => props.setGenForm((v) => ({ ...v, instruction: e.target.value }))}
            />
          </label>

          <div className="grid gap-2">
            <div className="text-xs text-subtext">上下文注入</div>
            <label className="flex items-center gap-2 text-sm text-ink">
              <input
                checked={props.genForm.context.include_world_setting}
                disabled={props.generating}
                onChange={(e) =>
                  props.setGenForm((v) => ({ ...v, context: { ...v.context, include_world_setting: e.target.checked } }))
                }
                type="checkbox"
              />
              世界观
            </label>
            <label className="flex items-center gap-2 text-sm text-ink">
              <input
                checked={props.genForm.context.include_style_guide}
                disabled={props.generating}
                onChange={(e) =>
                  props.setGenForm((v) => ({ ...v, context: { ...v.context, include_style_guide: e.target.checked } }))
                }
                type="checkbox"
              />
              风格
            </label>
            <label className="flex items-center gap-2 text-sm text-ink">
              <input
                checked={props.genForm.context.include_constraints}
                disabled={props.generating}
                onChange={(e) =>
                  props.setGenForm((v) => ({ ...v, context: { ...v.context, include_constraints: e.target.checked } }))
                }
                type="checkbox"
              />
              约束
            </label>
            <label className="flex items-center gap-2 text-sm text-ink">
              <input
                checked={props.genForm.context.include_outline}
                disabled={props.generating}
                onChange={(e) =>
                  props.setGenForm((v) => ({ ...v, context: { ...v.context, include_outline: e.target.checked } }))
                }
                type="checkbox"
              />
              大纲
            </label>
          </div>

          <label className="grid gap-1">
            <span className="text-xs text-subtext">上一章注入</span>
            <select
              className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink outline-none disabled:opacity-60"
              disabled={props.generating}
              value={props.genForm.context.previous_chapter}
              onChange={(e) =>
                props.setGenForm((v) => ({
                  ...v,
                  context: { ...v.context, previous_chapter: e.target.value as GenerateForm["context"]["previous_chapter"] },
                }))
              }
            >
              <option value="none">不注入</option>
              <option value="summary">摘要</option>
              <option value="content">正文</option>
            </select>
          </label>

          <div className="grid gap-2">
            <div className="text-xs text-subtext">注入角色（可选）</div>
            {props.characters.length === 0 ? <div className="text-sm text-subtext">暂无角色</div> : null}
            <div className="max-h-40 overflow-auto rounded-atelier border border-border bg-surface p-2">
              {props.characters.map((c) => (
                <label key={c.id} className="flex items-center gap-2 px-2 py-1 text-sm text-ink">
                  <input
                    checked={props.genForm.context.character_ids.includes(c.id)}
                    disabled={props.generating}
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

          <div className="rounded-atelier border border-border bg-surface p-3 text-xs text-subtext">
            生成结果不会自动保存到数据库，请生成后点击“保存”。
          </div>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink hover:bg-canvas disabled:opacity-60"
            disabled={props.generating || !props.activeChapter}
            onClick={props.onGenerateAppend}
            type="button"
          >
            {props.generating ? "生成中..." : "生成草稿（追加）"}
          </button>
          <button
            className="rounded-atelier bg-accent px-3 py-2 text-sm text-white hover:opacity-90 disabled:opacity-60"
            disabled={props.generating || !props.activeChapter}
            onClick={props.onGenerateReplace}
            type="button"
          >
            {props.generating ? "生成中..." : "生成草稿（替换）"}
          </button>
        </div>
      </div>
    </div>
  );
}

