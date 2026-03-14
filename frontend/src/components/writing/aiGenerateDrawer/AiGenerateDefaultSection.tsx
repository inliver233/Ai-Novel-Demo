import type { Dispatch, SetStateAction } from "react";

import { UI_COPY } from "../../../lib/uiCopy";
import type { Character } from "../../../types";
import type { GenerateForm } from "../types";
import { AI_GENERATE_DRAWER_COPY } from "./aiGenerateDrawerCopy";
import {
  AI_GENERATE_ADVANCED_MEMORY_MODULES,
  AI_GENERATE_CONTEXT_TOGGLES,
  AI_GENERATE_PRIMARY_MEMORY_MODULES,
  type ContextToggleKey,
  type MemoryModuleKey,
  type WritingStyle,
} from "./aiGenerateDrawerModels";

type Props = {
  generating: boolean;
  genForm: GenerateForm;
  setGenForm: Dispatch<SetStateAction<GenerateForm>>;
  characters: Character[];
  stylesLoading: boolean;
  presets: WritingStyle[];
  userStyles: WritingStyle[];
  styleHelperText: string;
};

export function AiGenerateDefaultSection(props: Props) {
  const updateMemoryModule = (key: MemoryModuleKey, checked: boolean) => {
    props.setGenForm((current) => ({
      ...current,
      memory_modules: { ...current.memory_modules, [key]: checked },
    }));
  };

  const updateContextToggle = (key: ContextToggleKey, checked: boolean) => {
    props.setGenForm((current) => ({
      ...current,
      context: { ...current.context, [key]: checked },
    }));
  };

  return (
    <>
      <div className="panel p-3">
        <div className="text-sm font-medium text-ink">{AI_GENERATE_DRAWER_COPY.basicSection.title}</div>
        <div className="mt-3 grid gap-3">
          <label className="grid gap-1">
            <span className="text-xs text-subtext">{AI_GENERATE_DRAWER_COPY.basicSection.instructionLabel}</span>
            <textarea
              className="textarea atelier-content"
              disabled={props.generating}
              name="instruction"
              rows={5}
              value={props.genForm.instruction}
              onChange={(event) => {
                const value = event.target.value;
                props.setGenForm((current) => ({ ...current, instruction: value }));
              }}
            />
          </label>

          <label className="grid gap-1">
            <span className="text-xs text-subtext">{AI_GENERATE_DRAWER_COPY.basicSection.targetWordCountLabel}</span>
            <input
              className="input"
              disabled={props.generating}
              min={100}
              name="target_word_count"
              type="number"
              value={props.genForm.target_word_count ?? ""}
              onChange={(event) => {
                const next = event.currentTarget.valueAsNumber;
                props.setGenForm((current) => ({
                  ...current,
                  target_word_count: Number.isNaN(next) ? null : next,
                }));
              }}
            />
          </label>

          <label className="grid gap-1">
            <span className="text-xs text-subtext">{AI_GENERATE_DRAWER_COPY.basicSection.styleLabel}</span>
            <select
              className="select"
              disabled={props.generating || props.stylesLoading}
              name="style_id"
              value={props.genForm.style_id ?? ""}
              onChange={(event) => {
                const value = event.target.value;
                props.setGenForm((current) => ({ ...current, style_id: value || null }));
              }}
              aria-label="gen_style_id"
            >
              <option value="">{AI_GENERATE_DRAWER_COPY.basicSection.styleAutoOption}</option>
              <optgroup label={AI_GENERATE_DRAWER_COPY.basicSection.systemStylesLabel}>
                {props.presets.map((style) => (
                  <option key={style.id} value={style.id}>
                    {style.name}
                  </option>
                ))}
              </optgroup>
              <optgroup label={AI_GENERATE_DRAWER_COPY.basicSection.userStylesLabel}>
                {props.userStyles.map((style) => (
                  <option key={style.id} value={style.id}>
                    {style.name}
                  </option>
                ))}
              </optgroup>
            </select>
            <div className="text-[11px] text-subtext">{props.styleHelperText}</div>
          </label>
        </div>
      </div>

      <div className="panel p-3">
        <div className="text-sm font-medium text-ink">{AI_GENERATE_DRAWER_COPY.memorySection.title}</div>

        <div className="mt-3">
          <label className="flex items-center justify-between gap-3 text-sm text-ink">
            <span>{UI_COPY.writing.memoryInjectionToggle}</span>
            <input
              className="checkbox"
              checked={props.genForm.memory_injection_enabled}
              disabled={props.generating}
              name="memory_injection_enabled"
              onChange={(event) => {
                const checked = event.target.checked;
                props.setGenForm((current) => ({ ...current, memory_injection_enabled: checked }));
              }}
              type="checkbox"
            />
          </label>
          <div className="mt-1 text-[11px] text-subtext">{UI_COPY.writing.memoryInjectionHint}</div>

          {props.genForm.memory_injection_enabled ? (
            <div className="mt-2 rounded-atelier border border-border bg-surface p-3">
              <label className="grid gap-1">
                <span className="text-xs text-subtext">{AI_GENERATE_DRAWER_COPY.memorySection.queryLabel}</span>
                <input
                  className="input"
                  disabled={props.generating}
                  aria-label="memory_query_text"
                  value={props.genForm.memory_query_text}
                  onChange={(event) => {
                    const value = event.currentTarget.value;
                    props.setGenForm((current) => ({ ...current, memory_query_text: value }));
                  }}
                />
              </label>
              <div className="mt-1 text-[11px] text-subtext">{AI_GENERATE_DRAWER_COPY.memorySection.queryHint}</div>

              <div className="mt-3 grid gap-2">
                <div className="text-xs text-subtext">{AI_GENERATE_DRAWER_COPY.memorySection.modulesLabel}</div>
                <div className="text-[11px] text-subtext">{AI_GENERATE_DRAWER_COPY.memorySection.modulesHint}</div>

                {AI_GENERATE_PRIMARY_MEMORY_MODULES.map((module) => (
                  <label key={module.key} className="flex items-center justify-between gap-3 text-sm text-ink">
                    <span>{module.label}</span>
                    <input
                      className="checkbox"
                      checked={props.genForm.memory_modules[module.key]}
                      disabled={props.generating}
                      onChange={(event) => updateMemoryModule(module.key, event.target.checked)}
                      type="checkbox"
                    />
                  </label>
                ))}

                <details className="rounded-atelier border border-border bg-surface p-2">
                  <summary className="cursor-pointer text-sm text-ink">
                    {AI_GENERATE_DRAWER_COPY.memorySection.advancedModulesTitle}
                  </summary>
                  <div className="mt-2 grid gap-2">
                    {AI_GENERATE_ADVANCED_MEMORY_MODULES.map((module) => (
                      <label key={module.key} className="flex items-center justify-between gap-3 text-sm text-ink">
                        <span>{module.label}</span>
                        <input
                          className="checkbox"
                          checked={props.genForm.memory_modules[module.key]}
                          disabled={props.generating}
                          onChange={(event) => updateMemoryModule(module.key, event.target.checked)}
                          type="checkbox"
                        />
                      </label>
                    ))}
                  </div>
                </details>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      <div className="panel p-3">
        <div className="text-sm font-medium text-ink">{AI_GENERATE_DRAWER_COPY.contextSection.title}</div>
        <div className="mt-3 grid gap-3">
          <div className="grid gap-2">
            <div className="text-xs text-subtext">{AI_GENERATE_DRAWER_COPY.contextSection.injectionLabel}</div>
            {AI_GENERATE_CONTEXT_TOGGLES.map((toggle) => (
              <label key={toggle.key} className="flex items-center gap-2 text-sm text-ink">
                <input
                  className="checkbox"
                  checked={props.genForm.context[toggle.key]}
                  disabled={props.generating}
                  name={toggle.inputName}
                  onChange={(event) => updateContextToggle(toggle.key, event.target.checked)}
                  type="checkbox"
                />
                {toggle.label}
              </label>
            ))}
          </div>

          <label className="grid gap-1">
            <span className="text-xs text-subtext">{AI_GENERATE_DRAWER_COPY.contextSection.previousChapterLabel}</span>
            <select
              className="select"
              disabled={props.generating}
              name="previous_chapter"
              value={props.genForm.context.previous_chapter}
              onChange={(event) => {
                const value = event.target.value as GenerateForm["context"]["previous_chapter"];
                props.setGenForm((current) => ({
                  ...current,
                  context: { ...current.context, previous_chapter: value },
                }));
              }}
            >
              <option value="none">{AI_GENERATE_DRAWER_COPY.contextSection.previousChapterNone}</option>
              <option value="tail">{AI_GENERATE_DRAWER_COPY.contextSection.previousChapterTail}</option>
              <option value="summary">{AI_GENERATE_DRAWER_COPY.contextSection.previousChapterSummary}</option>
              <option value="content">{AI_GENERATE_DRAWER_COPY.contextSection.previousChapterContent}</option>
            </select>
            <div className="text-[11px] text-subtext">{AI_GENERATE_DRAWER_COPY.contextSection.previousChapterHint}</div>
          </label>

          <div className="grid gap-2">
            <div className="text-xs text-subtext">{AI_GENERATE_DRAWER_COPY.contextSection.charactersLabel}</div>
            {props.characters.length === 0 ? (
              <div className="text-sm text-subtext">{AI_GENERATE_DRAWER_COPY.contextSection.charactersEmpty}</div>
            ) : null}
            <div className="max-h-40 overflow-auto rounded-atelier border border-border bg-surface p-2">
              {props.characters.map((character) => (
                <label key={character.id} className="flex items-center gap-2 px-2 py-1 text-sm text-ink">
                  <input
                    className="checkbox"
                    checked={props.genForm.context.character_ids.includes(character.id)}
                    disabled={props.generating}
                    name={`character_${character.id}`}
                    onChange={(event) => {
                      const checked = event.target.checked;
                      props.setGenForm((current) => {
                        const next = new Set(current.context.character_ids);
                        if (checked) next.add(character.id);
                        else next.delete(character.id);
                        return {
                          ...current,
                          context: { ...current.context, character_ids: Array.from(next) },
                        };
                      });
                    }}
                    type="checkbox"
                  />
                  <span className="truncate">{character.name}</span>
                </label>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
