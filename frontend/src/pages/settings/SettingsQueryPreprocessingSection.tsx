import type { Dispatch, SetStateAction } from "react";

import { RequestIdBadge } from "../../components/ui/RequestIdBadge";
import type { ProjectSettings } from "../../types";

import type { QpPreviewState, SettingsForm } from "./models";
import { SETTINGS_COPY } from "./settingsCopy";

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
      aria-label={SETTINGS_COPY.queryPreprocess.ariaLabel}
      open={props.qpPanelOpen}
      onToggle={(e) => props.onTogglePanel((e.currentTarget as HTMLDetailsElement).open)}
    >
      <summary className="ui-focus-ring ui-transition-fast cursor-pointer select-none p-6">
        <div className="grid gap-1">
          <div className="font-content text-xl text-ink">{SETTINGS_COPY.queryPreprocess.title}</div>
          <div className="text-xs text-subtext">{SETTINGS_COPY.queryPreprocess.subtitle}</div>
          <div className="text-xs text-subtext">{SETTINGS_COPY.queryPreprocess.featureHint}</div>
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
            {SETTINGS_COPY.queryPreprocess.enableLabel}
          </label>

          <div className="text-[11px] text-subtext">
            当前生效：{props.baselineSettings.query_preprocessing_effective?.enabled ? "enabled" : "disabled"}；来源：
            {props.baselineSettings.query_preprocessing_effective_source ?? "unknown"}
          </div>

          {props.settingsForm.query_preprocessing_enabled ? (
            <>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="grid gap-1">
                  <span className="text-xs text-subtext">{SETTINGS_COPY.queryPreprocess.tagsLabel}</span>
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
                  <div className="text-[11px] text-subtext">{SETTINGS_COPY.queryPreprocess.tagsHint}</div>
                  {props.queryPreprocessErr && props.queryPreprocessErrField === "tags" ? (
                    <div className="text-xs text-warning">{props.queryPreprocessErr}</div>
                  ) : null}
                </label>

                <label className="grid gap-1">
                  <span className="text-xs text-subtext">{SETTINGS_COPY.queryPreprocess.exclusionRulesLabel}</span>
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
                  <div className="text-[11px] text-subtext">{SETTINGS_COPY.queryPreprocess.exclusionRulesHint}</div>
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
                {SETTINGS_COPY.queryPreprocess.indexRefEnhanceLabel}
              </label>

              <div className="rounded-atelier border border-border bg-canvas p-4">
                <div className="text-sm text-ink">{SETTINGS_COPY.queryPreprocess.previewTitle}</div>
                <div className="mt-1 text-xs text-subtext">{SETTINGS_COPY.queryPreprocess.previewHint}</div>

                <label className="mt-3 grid gap-1 text-xs text-subtext">
                  query_text
                  <textarea
                    className="textarea mt-1 min-h-20 w-full"
                    value={props.qpPreviewQueryText}
                    onChange={(e) => props.onChangePreviewQueryText(e.target.value)}
                    placeholder={SETTINGS_COPY.queryPreprocess.previewPlaceholder}
                  />
                </label>

                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    className="btn btn-secondary"
                    disabled={props.qpPreviewLoading || !props.projectId}
                    onClick={props.onRunQpPreview}
                    type="button"
                  >
                    {props.qpPreviewLoading
                      ? SETTINGS_COPY.queryPreprocess.previewLoadingButton
                      : SETTINGS_COPY.queryPreprocess.previewButton}
                  </button>
                  <button
                    className="btn btn-secondary"
                    disabled={props.qpPreviewLoading}
                    onClick={props.onClearQpPreview}
                    type="button"
                  >
                    {SETTINGS_COPY.queryPreprocess.clearResultButton}
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
              {SETTINGS_COPY.queryPreprocess.emptyState}
            </div>
          )}
        </div>
      </div>
    </details>
  );
}
