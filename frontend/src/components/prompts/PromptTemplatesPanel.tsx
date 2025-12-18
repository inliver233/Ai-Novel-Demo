import type { Dispatch, SetStateAction } from "react";

import type { PromptForm, TemplatePreview } from "./types";

type Props = {
  promptForm: PromptForm;
  setPromptForm: Dispatch<SetStateAction<PromptForm>>;
  promptsDirty: boolean;
  saving: boolean;
  outlinePreview: TemplatePreview;
  chapterPreview: TemplatePreview;
  availablePlaceholdersText: string;
  onSave: () => void;
};

export function PromptTemplatesPanel(props: Props) {
  return (
    <section className="rounded-atelier border border-border bg-surface p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="font-content text-xl">Prompt 模板</div>
          <div className="mt-1 text-xs text-subtext">编辑/预览 outline_generate 与 chapter_generate</div>
        </div>
        <button
          className="rounded-atelier bg-accent px-3 py-2 text-sm text-white hover:opacity-90 disabled:opacity-60"
          disabled={!props.promptsDirty || props.saving}
          onClick={props.onSave}
          type="button"
        >
          保存
        </button>
      </div>

      <div className="mt-4 grid gap-6">
        <div className="grid gap-3">
          <div className="text-sm text-ink">outline_generate</div>
          <textarea
            className="atelier-mono rounded-atelier border border-border bg-canvas px-3 py-3 text-sm text-ink outline-none"
            name="outline_system_template"
            rows={4}
            value={props.promptForm.outline_generate.system_template}
            onChange={(e) =>
              props.setPromptForm((v) => ({
                ...v,
                outline_generate: { ...v.outline_generate, system_template: e.target.value },
              }))
            }
            placeholder="system_template"
          />
          <textarea
            className="atelier-mono rounded-atelier border border-border bg-canvas px-3 py-3 text-sm text-ink outline-none"
            name="outline_user_template"
            rows={7}
            value={props.promptForm.outline_generate.user_template}
            onChange={(e) =>
              props.setPromptForm((v) => ({ ...v, outline_generate: { ...v.outline_generate, user_template: e.target.value } }))
            }
            placeholder="user_template"
          />
          <div className="rounded-atelier border border-border bg-canvas p-4">
            <div className="text-xs text-subtext">预览缺失占位符：{props.outlinePreview.missing.join(", ") || "无"}</div>
            <div className="mt-3 grid gap-2">
              <div className="text-xs text-subtext">system</div>
              <pre className="atelier-mono whitespace-pre-wrap text-xs text-ink">{props.outlinePreview.system}</pre>
              <div className="text-xs text-subtext">user</div>
              <pre className="atelier-mono whitespace-pre-wrap text-xs text-ink">{props.outlinePreview.user}</pre>
            </div>
          </div>
        </div>

        <div className="grid gap-3">
          <div className="text-sm text-ink">chapter_generate</div>
          <textarea
            className="atelier-mono rounded-atelier border border-border bg-canvas px-3 py-3 text-sm text-ink outline-none"
            name="chapter_system_template"
            rows={4}
            value={props.promptForm.chapter_generate.system_template}
            onChange={(e) =>
              props.setPromptForm((v) => ({ ...v, chapter_generate: { ...v.chapter_generate, system_template: e.target.value } }))
            }
            placeholder="system_template"
          />
          <textarea
            className="atelier-mono rounded-atelier border border-border bg-canvas px-3 py-3 text-sm text-ink outline-none"
            name="chapter_user_template"
            rows={7}
            value={props.promptForm.chapter_generate.user_template}
            onChange={(e) =>
              props.setPromptForm((v) => ({ ...v, chapter_generate: { ...v.chapter_generate, user_template: e.target.value } }))
            }
            placeholder="user_template"
          />
          <div className="rounded-atelier border border-border bg-canvas p-4">
            <div className="text-xs text-subtext">预览缺失占位符：{props.chapterPreview.missing.join(", ") || "无"}</div>
            <div className="mt-3 grid gap-2">
              <div className="text-xs text-subtext">system</div>
              <pre className="atelier-mono whitespace-pre-wrap text-xs text-ink">{props.chapterPreview.system}</pre>
              <div className="text-xs text-subtext">user</div>
              <pre className="atelier-mono whitespace-pre-wrap text-xs text-ink">{props.chapterPreview.user}</pre>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-4 text-xs text-subtext">可用占位符：{props.availablePlaceholdersText}</div>
    </section>
  );
}
