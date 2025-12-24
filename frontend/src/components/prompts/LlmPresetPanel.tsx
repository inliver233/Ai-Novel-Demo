import type { Dispatch, SetStateAction } from "react";

import type { LLMProfile, LLMProvider } from "../../types";
import type { LlmForm } from "./types";

type Props = {
  llmForm: LlmForm;
  setLlmForm: Dispatch<SetStateAction<LlmForm>>;
  presetDirty: boolean;
  saving: boolean;
  testing: boolean;
  onTestConnection: () => void;
  onSave: () => void;

  profiles: LLMProfile[];
  selectedProfileId: string | null;
  onSelectProfile: (profileId: string | null) => void;
  profileName: string;
  onChangeProfileName: (value: string) => void;
  profileBusy: boolean;
  onCreateProfile: () => void;
  onUpdateProfile: () => void;
  onDeleteProfile: () => void;

  lockConnectionFields: boolean;

  apiKey: string;
  onChangeApiKey: (value: string) => void;
  onSaveApiKey: () => void;
  onClearApiKey: () => void;
};

export function LlmPresetPanel(props: Props) {
  const selectedProfile = props.selectedProfileId
    ? (props.profiles.find((p) => p.id === props.selectedProfileId) ?? null)
    : null;

  return (
    <section className="panel p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="font-content text-xl">模型配置</div>
          <div className="mt-1 text-xs text-subtext">
            provider/base_url/model/参数（API Key 安全存储在后端，不回显明文）
          </div>
        </div>
        <div className="flex gap-2">
          <button className="btn btn-secondary" disabled={props.testing} onClick={props.onTestConnection} type="button">
            {props.testing ? "测试中..." : "测试连接"}
          </button>
          <button
            className="btn btn-primary"
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
            className="select"
            name="provider"
            value={props.llmForm.provider}
            disabled={props.lockConnectionFields}
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
            className="input"
            disabled={props.lockConnectionFields}
            name="model"
            value={props.llmForm.model}
            onChange={(e) => props.setLlmForm((v) => ({ ...v, model: e.target.value }))}
          />
        </label>

        <label className="grid gap-1 sm:col-span-2">
          <span className="text-xs text-subtext">Base URL</span>
          <input
            className="input"
            placeholder={props.llmForm.provider === "openai_compatible" ? "https://your-proxy.com/v1" : undefined}
            disabled={props.lockConnectionFields}
            name="base_url"
            value={props.llmForm.base_url}
            onChange={(e) => props.setLlmForm((v) => ({ ...v, base_url: e.target.value }))}
          />
        </label>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-3">
        <label className="grid gap-1">
          <span className="text-xs text-subtext">temperature</span>
          <input
            className="input"
            name="temperature"
            value={props.llmForm.temperature}
            onChange={(e) => props.setLlmForm((v) => ({ ...v, temperature: e.target.value }))}
          />
        </label>
        <label className="grid gap-1">
          <span className="text-xs text-subtext">top_p</span>
          <input
            className="input"
            name="top_p"
            value={props.llmForm.top_p}
            onChange={(e) => props.setLlmForm((v) => ({ ...v, top_p: e.target.value }))}
          />
        </label>
        <label className="grid gap-1">
          <span className="text-xs text-subtext">max_tokens</span>
          <input
            className="input"
            name="max_tokens"
            value={props.llmForm.max_tokens}
            onChange={(e) => props.setLlmForm((v) => ({ ...v, max_tokens: e.target.value }))}
          />
        </label>
        {props.llmForm.provider === "openai" || props.llmForm.provider === "openai_compatible" ? (
          <>
            <label className="grid gap-1">
              <span className="text-xs text-subtext">presence_penalty</span>
              <input
                className="input"
                name="presence_penalty"
                value={props.llmForm.presence_penalty}
                onChange={(e) => props.setLlmForm((v) => ({ ...v, presence_penalty: e.target.value }))}
              />
            </label>
            <label className="grid gap-1">
              <span className="text-xs text-subtext">frequency_penalty</span>
              <input
                className="input"
                name="frequency_penalty"
                value={props.llmForm.frequency_penalty}
                onChange={(e) => props.setLlmForm((v) => ({ ...v, frequency_penalty: e.target.value }))}
              />
            </label>
          </>
        ) : (
          <label className="grid gap-1">
            <span className="text-xs text-subtext">top_k</span>
            <input
              className="input"
              name="top_k"
              value={props.llmForm.top_k}
              onChange={(e) => props.setLlmForm((v) => ({ ...v, top_k: e.target.value }))}
            />
          </label>
        )}
        <label className="grid gap-1 sm:col-span-2">
          <span className="text-xs text-subtext">stop（逗号分隔）</span>
          <input
            className="input"
            placeholder="---"
            name="stop"
            value={props.llmForm.stop}
            onChange={(e) => props.setLlmForm((v) => ({ ...v, stop: e.target.value }))}
          />
        </label>
        <label className="grid gap-1">
          <span className="text-xs text-subtext">timeout_seconds（默认 90；最大 1800/30分钟）</span>
          <input
            className="input"
            name="timeout_seconds"
            value={props.llmForm.timeout_seconds}
            onChange={(e) => props.setLlmForm((v) => ({ ...v, timeout_seconds: e.target.value }))}
          />
        </label>
        <label className="grid gap-1 sm:col-span-3">
          <span className="text-xs text-subtext">extra（JSON）</span>
          <textarea
            className="textarea atelier-mono"
            name="extra"
            rows={5}
            value={props.llmForm.extra}
            onChange={(e) => props.setLlmForm((v) => ({ ...v, extra: e.target.value }))}
          />
        </label>
      </div>

      <div className="surface mt-4 p-4">
        <div className="text-sm text-ink">API 配置库（后端持久化）</div>
        <div className="mt-2 grid gap-3 sm:grid-cols-3">
          <label className="grid gap-1 sm:col-span-2">
            <span className="text-xs text-subtext">选择配置</span>
            <select
              className="select"
              name="profile_select"
              value={props.selectedProfileId ?? ""}
              disabled={props.profileBusy}
              onChange={(e) => props.onSelectProfile(e.target.value ? e.target.value : null)}
            >
              <option value="">（未绑定后端配置）</option>
              {props.profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} · {p.provider}/{p.model}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1 sm:col-span-1">
            <span className="text-xs text-subtext">新建配置名</span>
            <input
              className="input"
              disabled={props.profileBusy}
              name="profile_name"
              value={props.profileName}
              onChange={(e) => props.onChangeProfileName(e.target.value)}
              placeholder="例如：AI-Wave 网关"
            />
          </label>
        </div>

        {selectedProfile ? (
          <div className="mt-3 text-xs text-subtext">
            当前：{selectedProfile.name}（{selectedProfile.provider}/{selectedProfile.model}）
          </div>
        ) : (
          <div className="mt-3 text-xs text-subtext">
            当前：未绑定配置（生成/测试连接会提示先在“模型配置”页选择/新建配置并保存 Key）
          </div>
        )}

        <div className="mt-3 flex flex-wrap gap-2">
          <button
            className="btn btn-secondary px-3 py-2 text-xs"
            disabled={props.profileBusy}
            onClick={props.onCreateProfile}
            type="button"
          >
            保存为新配置
          </button>
          <button
            className="btn btn-secondary px-3 py-2 text-xs"
            disabled={props.profileBusy || !props.selectedProfileId}
            onClick={props.onUpdateProfile}
            type="button"
          >
            更新当前配置
          </button>
          <button
            className="btn btn-ghost px-3 py-2 text-xs text-accent hover:bg-accent/10"
            disabled={props.profileBusy || !props.selectedProfileId}
            onClick={props.onDeleteProfile}
            type="button"
          >
            删除当前配置
          </button>
        </div>
      </div>

      <div className="surface mt-4 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-sm text-ink">API Key（后端安全存储）</div>
          <div className="flex flex-wrap gap-2">
            <button
              className="btn btn-secondary px-3 py-2 text-xs"
              disabled={!props.selectedProfileId || props.profileBusy || !selectedProfile?.has_api_key}
              onClick={props.onClearApiKey}
              type="button"
            >
              清除 Key
            </button>
          </div>
        </div>
        <div className="mt-2 text-xs text-subtext">
          {selectedProfile
            ? selectedProfile.has_api_key
              ? `已保存：${selectedProfile.masked_api_key ?? "（已保存）"}`
              : "未保存：请在下方输入并保存"
            : "请先选择/新建一个后端配置（配置库）再保存 Key"}
        </div>
        <div className="mt-2 flex gap-2">
          <input
            className="input flex-1"
            placeholder="输入新 Key（不会回显已保存的 Key）"
            name="api_key"
            type="password"
            value={props.apiKey}
            onChange={(e) => props.onChangeApiKey(e.target.value)}
          />
          <button
            className="btn btn-primary"
            disabled={!props.selectedProfileId || props.profileBusy || !props.apiKey.trim()}
            onClick={props.onSaveApiKey}
            type="button"
          >
            保存 Key
          </button>
        </div>
      </div>
    </section>
  );
}
