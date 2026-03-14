import type { Dispatch, SetStateAction } from "react";

import type { GenerateForm } from "../types";
import { AI_GENERATE_DRAWER_COPY } from "./aiGenerateDrawerCopy";

type Props = {
  advancedOpen: boolean;
  advancedPanelId: string;
  autoReliableTransport: boolean;
  generating: boolean;
  genForm: GenerateForm;
  setAdvancedOpen: Dispatch<SetStateAction<boolean>>;
  setGenForm: Dispatch<SetStateAction<GenerateForm>>;
  showUnsupportedStreamWarning: boolean;
};

export function AiGenerateAdvancedSection(props: Props) {
  return (
    <div className="panel p-3">
      <button
        className="ui-focus-ring ui-pressable flex w-full items-center justify-between gap-3 rounded-atelier px-2 py-2 text-left hover:bg-canvas"
        aria-controls={props.advancedPanelId}
        aria-expanded={props.advancedOpen}
        onClick={() => props.setAdvancedOpen((open) => !open)}
        type="button"
      >
        <span className="text-sm font-medium text-ink">{AI_GENERATE_DRAWER_COPY.advancedSection.title}</span>
        <span aria-hidden="true" className="text-xs text-subtext">
          {props.advancedOpen
            ? AI_GENERATE_DRAWER_COPY.advancedSection.collapse
            : AI_GENERATE_DRAWER_COPY.advancedSection.expand}
        </span>
      </button>

      {!props.advancedOpen ? (
        <div className="mt-2 text-[11px] text-subtext">{AI_GENERATE_DRAWER_COPY.advancedSection.collapsedHint}</div>
      ) : null}

      {props.autoReliableTransport ? (
        <div className="mt-2 text-xs text-warning">
          {AI_GENERATE_DRAWER_COPY.advancedSection.reliableTransportWarning}
        </div>
      ) : null}

      {props.showUnsupportedStreamWarning ? (
        <div className="mt-2 text-xs text-warning">
          {AI_GENERATE_DRAWER_COPY.advancedSection.unsupportedStreamWarning}
        </div>
      ) : null}

      {props.advancedOpen ? (
        <div className="mt-3 grid gap-2" id={props.advancedPanelId}>
          <label className="flex items-center justify-between gap-3 text-sm text-ink">
            <span>{AI_GENERATE_DRAWER_COPY.advancedSection.stream}</span>
            <input
              className="checkbox"
              checked={props.genForm.stream}
              disabled={props.generating}
              name="stream"
              onChange={(event) => {
                const checked = event.target.checked;
                props.setGenForm((current) => ({ ...current, stream: checked }));
              }}
              type="checkbox"
            />
          </label>

          <label className="flex items-center justify-between gap-3 text-sm text-ink">
            <span>{AI_GENERATE_DRAWER_COPY.advancedSection.planFirst}</span>
            <input
              className="checkbox"
              checked={props.genForm.plan_first}
              disabled={props.generating}
              name="plan_first"
              onChange={(event) => {
                const checked = event.target.checked;
                props.setGenForm((current) => ({ ...current, plan_first: checked }));
              }}
              type="checkbox"
            />
          </label>

          <label className="flex items-center justify-between gap-3 text-sm text-ink">
            <span>{AI_GENERATE_DRAWER_COPY.advancedSection.postEdit}</span>
            <input
              className="checkbox"
              checked={props.genForm.post_edit}
              disabled={props.generating}
              name="post_edit"
              onChange={(event) => {
                const checked = event.target.checked;
                props.setGenForm((current) => ({
                  ...current,
                  post_edit: checked,
                  post_edit_sanitize: checked ? current.post_edit_sanitize : false,
                }));
              }}
              type="checkbox"
            />
          </label>

          <label className="flex items-center justify-between gap-3 text-sm text-ink">
            <span>{AI_GENERATE_DRAWER_COPY.advancedSection.postEditSanitize}</span>
            <input
              className="checkbox"
              checked={props.genForm.post_edit_sanitize}
              disabled={props.generating || !props.genForm.post_edit}
              name="post_edit_sanitize"
              onChange={(event) => {
                const checked = event.target.checked;
                props.setGenForm((current) => ({ ...current, post_edit_sanitize: checked }));
              }}
              type="checkbox"
            />
          </label>

          <label className="flex items-center justify-between gap-3 text-sm text-ink">
            <span>{AI_GENERATE_DRAWER_COPY.advancedSection.contentOptimize}</span>
            <input
              className="checkbox"
              checked={props.genForm.content_optimize}
              disabled={props.generating}
              name="content_optimize"
              onChange={(event) => {
                const checked = event.target.checked;
                props.setGenForm((current) => ({ ...current, content_optimize: checked }));
              }}
              type="checkbox"
            />
          </label>
          <div className="text-[11px] text-subtext">{AI_GENERATE_DRAWER_COPY.advancedSection.failSoftHint}</div>
        </div>
      ) : (
        <div id={props.advancedPanelId} hidden />
      )}
    </div>
  );
}
