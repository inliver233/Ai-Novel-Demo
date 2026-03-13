import { UI_COPY } from "../../lib/uiCopy";

import { SETTINGS_COPY } from "./settingsCopy";

type SettingsFeatureDefaultsSectionProps = {
  writingMemoryInjectionEnabled: boolean;
  onChangeWritingMemoryInjectionEnabled: (enabled: boolean) => void;
  onResetWritingMemoryInjectionEnabled: () => void;
};

export function SettingsFeatureDefaultsSection(props: SettingsFeatureDefaultsSectionProps) {
  return (
    <details className="panel" aria-label={UI_COPY.featureDefaults.ariaLabel}>
      <summary className="ui-focus-ring ui-transition-fast cursor-pointer select-none p-6">
        <div className="grid gap-1">
          <div className="font-content text-xl text-ink">{UI_COPY.featureDefaults.title}</div>
          <div className="text-xs text-subtext">{UI_COPY.featureDefaults.subtitle}</div>
          <div className="text-xs text-subtext">
            {SETTINGS_COPY.featureDefaults.status(props.writingMemoryInjectionEnabled)}
          </div>
        </div>
      </summary>

      <div className="px-6 pb-6 pt-0">
        <div className="mt-4 grid gap-2">
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              id="settings_writing_memory_injection_default"
              name="writing_memory_injection_default"
              checked={props.writingMemoryInjectionEnabled}
              onChange={(e) => props.onChangeWritingMemoryInjectionEnabled(e.target.checked)}
              aria-label="settings_writing_memory_injection_default"
              type="checkbox"
            />
            {UI_COPY.featureDefaults.memoryInjectionLabel}
          </label>
          <div className="text-[11px] text-subtext">{UI_COPY.featureDefaults.memoryInjectionHint}</div>

          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button
              className="btn btn-secondary btn-sm"
              onClick={props.onResetWritingMemoryInjectionEnabled}
              type="button"
            >
              {UI_COPY.featureDefaults.reset}
            </button>
            <div className="text-[11px] text-subtext">{UI_COPY.featureDefaults.resetHint}</div>
          </div>

          <div className="mt-3 rounded-atelier border border-border bg-canvas p-3 text-[11px] text-subtext">
            {UI_COPY.featureDefaults.autoUpdateHint}
          </div>
        </div>
      </div>
    </details>
  );
}
