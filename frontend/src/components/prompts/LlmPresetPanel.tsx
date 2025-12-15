import type { Dispatch, SetStateAction } from "react";

import type { LLMProvider } from "../../types";
import type { LlmForm } from "./types";

type Props = {
  llmForm: LlmForm;
  setLlmForm: Dispatch<SetStateAction<LlmForm>>;
  presetDirty: boolean;
  saving: boolean;
  testing: boolean;
  onTestConnection: () => void;
  onSave: () => void;

  apiKeyVisible: boolean;
  onToggleApiKeyVisible: () => void;
  apiKey: string;
  onChangeApiKey: (value: string) => void;
  onSaveApiKey: () => void;
  onClearApiKey: () => void;
};

export function LlmPresetPanel(props: Props) {
  return (
    <section className="rounded-atelier border border-border bg-surface p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="font-content text-xl">模型配置</div>
          <div className="mt-1 text-xs text-subtext">provider/base_url/model/参数（Key 仅保存在本机）</div>
        </div>
        <div className="flex gap-2">
          <button
            className="rounded-atelier border border-border bg-canvas px-3 py-2 text-sm text-ink hover:bg-surface disabled:opacity-60"
            disabled={props.testing}
            onClick={props.onTestConnection}
            type="button"
          >
            {props.testing ? "测试中..." : "测试连接"}
          </button>
          <button
            className="rounded-atelier bg-accent px-3 py-2 text-sm text-white hover:opacity-90 disabled:opacity-60"
            disabled={!props.presetDirty || props.saving}
            onClick={props.onSave}
            type="button"
          >
            保存
          </button>
        </div>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <label className="grid gap-1">
          <span className="text-xs text-subtext">Provider</span>
          <select
            className="rounded-atelier border border-border bg-canvas px-3 py-2 text-sm text-ink"
            value={props.llmForm.provider}
            onChange={(e) =>
              props.setLlmForm((v) => ({
                ...v,
                provider: e.target.value as LLMProvider,
              }))
            }
          >
            <option value="openai">openai（官方）</option>
            <option value="openai_compatible">openai_compatible（中转/本地）</option>
            <option value="anthropic">anthropic（Claude）</option>
            <option value="gemini">gemini</option>
          </select>
        </label>
        <label className="grid gap-1">
          <span className="text-xs text-subtext">Model</span>
          <input
            className="rounded-atelier border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none"
            value={props.llmForm.model}
            onChange={(e) => props.setLlmForm((v) => ({ ...v, model: e.target.value }))}
          />
        </label>

        <label className="grid gap-1 sm:col-span-2">
          <span className="text-xs text-subtext">Base URL</span>
          <input
            className="rounded-atelier border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none"
            placeholder={props.llmForm.provider === "openai_compatible" ? "https://your-proxy.com/v1" : undefined}
            value={props.llmForm.base_url}
            onChange={(e) => props.setLlmForm((v) => ({ ...v, base_url: e.target.value }))}
          />
        </label>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-3">
        <label className="grid gap-1">
          <span className="text-xs text-subtext">temperature</span>
          <input
            className="rounded-atelier border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none"
            value={props.llmForm.temperature}
            onChange={(e) => props.setLlmForm((v) => ({ ...v, temperature: e.target.value }))}
          />
        </label>
        <label className="grid gap-1">
          <span className="text-xs text-subtext">top_p</span>
          <input
            className="rounded-atelier border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none"
            value={props.llmForm.top_p}
            onChange={(e) => props.setLlmForm((v) => ({ ...v, top_p: e.target.value }))}
          />
        </label>
        <label className="grid gap-1">
          <span className="text-xs text-subtext">max_tokens</span>
          <input
            className="rounded-atelier border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none"
            value={props.llmForm.max_tokens}
            onChange={(e) => props.setLlmForm((v) => ({ ...v, max_tokens: e.target.value }))}
          />
        </label>
        {props.llmForm.provider === "openai" || props.llmForm.provider === "openai_compatible" ? (
          <>
            <label className="grid gap-1">
              <span className="text-xs text-subtext">presence_penalty</span>
              <input
                className="rounded-atelier border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none"
                value={props.llmForm.presence_penalty}
                onChange={(e) => props.setLlmForm((v) => ({ ...v, presence_penalty: e.target.value }))}
              />
            </label>
            <label className="grid gap-1">
              <span className="text-xs text-subtext">frequency_penalty</span>
              <input
                className="rounded-atelier border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none"
                value={props.llmForm.frequency_penalty}
                onChange={(e) => props.setLlmForm((v) => ({ ...v, frequency_penalty: e.target.value }))}
              />
            </label>
          </>
        ) : (
          <label className="grid gap-1">
            <span className="text-xs text-subtext">top_k</span>
            <input
              className="rounded-atelier border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none"
              value={props.llmForm.top_k}
              onChange={(e) => props.setLlmForm((v) => ({ ...v, top_k: e.target.value }))}
            />
          </label>
        )}
        <label className="grid gap-1 sm:col-span-2">
          <span className="text-xs text-subtext">stop（逗号分隔）</span>
          <input
            className="rounded-atelier border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none"
            placeholder="---"
            value={props.llmForm.stop}
            onChange={(e) => props.setLlmForm((v) => ({ ...v, stop: e.target.value }))}
          />
        </label>
        <label className="grid gap-1">
          <span className="text-xs text-subtext">timeout_seconds（默认 90；最大 1800/30分钟）</span>
          <input
            className="rounded-atelier border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none"
            value={props.llmForm.timeout_seconds}
            onChange={(e) => props.setLlmForm((v) => ({ ...v, timeout_seconds: e.target.value }))}
          />
        </label>
        <label className="grid gap-1 sm:col-span-3">
          <span className="text-xs text-subtext">extra（JSON）</span>
          <textarea
            className="atelier-mono rounded-atelier border border-border bg-canvas px-3 py-3 text-sm text-ink outline-none"
            rows={5}
            value={props.llmForm.extra}
            onChange={(e) => props.setLlmForm((v) => ({ ...v, extra: e.target.value }))}
          />
        </label>
      </div>

      <div className="mt-4 rounded-atelier border border-border bg-canvas p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="text-sm text-ink">API Key（仅保存在本机 localStorage）</div>
          <div className="flex gap-2">
            <button
              className="rounded-atelier border border-border bg-surface px-3 py-2 text-xs text-ink hover:bg-canvas"
              onClick={props.onToggleApiKeyVisible}
              type="button"
            >
              {props.apiKeyVisible ? "隐藏" : "显示"}
            </button>
            <button
              className="rounded-atelier border border-border bg-surface px-3 py-2 text-xs text-ink hover:bg-canvas"
              onClick={props.onClearApiKey}
              type="button"
            >
              清除
            </button>
          </div>
        </div>
        <div className="mt-2 flex gap-2">
          <input
            className="flex-1 rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink outline-none"
            placeholder="sk-..."
            type={props.apiKeyVisible ? "text" : "password"}
            value={props.apiKey}
            onChange={(e) => props.onChangeApiKey(e.target.value)}
          />
          <button
            className="rounded-atelier bg-ink px-3 py-2 text-sm text-canvas hover:opacity-90"
            onClick={props.onSaveApiKey}
            type="button"
          >
            本地保存
          </button>
        </div>
      </div>
    </section>
  );
}
