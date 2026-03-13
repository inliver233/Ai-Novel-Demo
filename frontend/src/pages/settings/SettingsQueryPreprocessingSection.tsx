import type { Dispatch, SetStateAction } from "react";

import { RequestIdBadge } from "../../components/ui/RequestIdBadge";
import type { ProjectSettings } from "../../types";

import type { QpPreviewState, SettingsForm } from "./models";

type SettingsQueryPreprocessingSectionProps = {
  baselineSettings: ProjectSettings;
  settingsForm: SettingsForm;
  setSettingsForm: Dispatch<SetStateAction<SettingsForm>>;
  qpPanelOpen: boolean;
  onTogglePanel: (open: boolean) => void;
  queryPreprocessErr: string | null;
  queryPreprocessErrField: "tags" | "exclusion_rules" | null;
  qpPreviewQueryText: string;
  onChangePreviewQueryText: (value: string) => void;
  qpPreviewLoading: boolean;
  qpPreview: QpPreviewState | null;
  qpPreviewError: string | null;
  projectId?: string;
  onRunQpPreview: () => void;
  onClearQpPreview: () => void;
};

export function SettingsQueryPreprocessingSection(props: SettingsQueryPreprocessingSectionProps) {
  return (
    <details
      className="panel"
      aria-label="Query 预处理（Query Preprocessing）"
      open={props.qpPanelOpen}
      onToggle={(e) => props.onTogglePanel((e.currentTarget as HTMLDetailsElement).open)}
    >
      <summary className="ui-focus-ring ui-transition-fast cursor-pointer select-none p-6">
        <div className="grid gap-1">
          <div className="font-content text-xl text-ink">Query 预处理（Query Preprocessing）</div>
          <div className="text-xs text-subtext">
            用于把 query_text 先“标准化/去噪”，让 WorldBook / Vector RAG / Graph 的检索更稳定（默认关闭）。
          </div>
          <div className="text-xs text-subtext">
            功能：提取 #tag、移除 exclusion_rules、可选识别章节引用（index_ref_enhance）。
          </div>
        </div>
      </summary>

      <div className="px-6 pb-6 pt-0">
        <div className="mt-4 grid gap-4">
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              checked={props.settingsForm.query_preprocessing_enabled}
              onChange={(e) =>
                props.setSettingsForm((value) => ({ ...value, query_preprocessing_enabled: e.target.checked }))
              }
              type="checkbox"
            />
            启用 query_preprocessing（默认关闭）
          </label>

          <div className="text-[11px] text-subtext">
            当前生效：{props.baselineSettings.query_preprocessing_effective?.enabled ? "enabled" : "disabled"}；来源：
            {props.baselineSettings.query_preprocessing_effective_source ?? "unknown"}
          </div>

          {props.settingsForm.query_preprocessing_enabled ? (
            <>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="grid gap-1">
                  <span className="text-xs text-subtext">tags（每行一条；匹配 #tag；留空=提取所有 tag）</span>
                  <textarea
                    className="textarea"
                    name="query_preprocessing_tags"
                    rows={5}
                    value={props.settingsForm.query_preprocessing_tags}
                    onChange={(e) =>
                      props.setSettingsForm((value) => ({ ...value, query_preprocessing_tags: e.target.value }))
                    }
                    placeholder={"例如：\nfoo\nbar"}
                  />
                  <div className="text-[11px] text-subtext">最大 50 条；每条最多 64 字符。</div>
                  {props.queryPreprocessErr && props.queryPreprocessErrField === "tags" ? (
                    <div className="text-xs text-warning">{props.queryPreprocessErr}</div>
                  ) : null}
                </label>

                <label className="grid gap-1">
                  <span className="text-xs text-subtext">exclusion_rules（每行一条；出现则移除）</span>
                  <textarea
                    className="textarea"
                    name="query_preprocessing_exclusion_rules"
                    rows={5}
                    value={props.settingsForm.query_preprocessing_exclusion_rules}
                    onChange={(e) =>
                      props.setSettingsForm((value) => ({
                        ...value,
                        query_preprocessing_exclusion_rules: e.target.value,
                      }))
                    }
                    placeholder={"例如：\n忽略这段\nREMOVE"}
                  />
                  <div className="text-[11px] text-subtext">最大 50 条；每条最多 256 字符。</div>
                  {props.queryPreprocessErr && props.queryPreprocessErrField === "exclusion_rules" ? (
                    <div className="text-xs text-warning">{props.queryPreprocessErr}</div>
                  ) : null}
                </label>
              </div>

              <label className="flex items-center gap-2 text-sm text-ink">
                <input
                  className="checkbox"
                  checked={props.settingsForm.query_preprocessing_index_ref_enhance}
                  onChange={(e) =>
                    props.setSettingsForm((value) => ({
                      ...value,
                      query_preprocessing_index_ref_enhance: e.target.checked,
                    }))
                  }
                  type="checkbox"
                />
                index_ref_enhance（识别“第N章 / chapter N”并追加引用 token）
              </label>

              <div className="rounded-atelier border border-border bg-canvas p-4">
                <div className="text-sm text-ink">示例 normalize（基于已保存的 effective 配置）</div>
                <div className="mt-1 text-xs text-subtext">修改配置后请先保存，再点击预览。</div>

                <label className="mt-3 grid gap-1 text-xs text-subtext">
                  query_text
                  <textarea
                    className="textarea mt-1 min-h-20 w-full"
                    value={props.qpPreviewQueryText}
                    onChange={(e) => props.onChangePreviewQueryText(e.target.value)}
                    placeholder="例如：回顾第1章 #foo REMOVE"
                  />
                </label>

                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    className="btn btn-secondary"
                    disabled={props.qpPreviewLoading || !props.projectId}
                    onClick={props.onRunQpPreview}
                    type="button"
                  >
                    {props.qpPreviewLoading ? "预览中…" : "预览"}
                  </button>
                  <button
                    className="btn btn-secondary"
                    disabled={props.qpPreviewLoading}
                    onClick={props.onClearQpPreview}
                    type="button"
                  >
                    清空结果
                  </button>
                </div>

                {props.qpPreviewError ? <div className="mt-3 text-xs text-warning">{props.qpPreviewError}</div> : null}

                {props.qpPreview ? (
                  <div className="mt-3 grid gap-3">
                    <RequestIdBadge requestId={props.qpPreview.requestId} />
                    <div>
                      <div className="text-xs text-subtext">normalized_query_text</div>
                      <pre className="mt-1 max-h-40 overflow-auto rounded-atelier border border-border bg-surface p-3 text-xs text-ink">
                        {props.qpPreview.normalized}
                      </pre>
                    </div>
                    <details>
                      <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                        preprocess_obs
                      </summary>
                      <pre className="mt-2 max-h-64 overflow-auto rounded-atelier border border-border bg-surface p-3 text-xs text-ink">
                        {JSON.stringify(props.qpPreview.obs ?? null, null, 2)}
                      </pre>
                    </details>
                  </div>
                ) : null}
              </div>
            </>
          ) : (
            <div className="rounded-atelier border border-border bg-canvas p-4 text-xs text-subtext">
              启用后可配置 tags / exclusion_rules，并可在下方预览 normalized_query_text（保存后生效）。
            </div>
          )}
        </div>
      </div>
    </details>
  );
}
