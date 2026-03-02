import { useCallback, useMemo } from "react";
import type { Dispatch, SetStateAction } from "react";

import type { LLMProfile, LLMProvider } from "../../types";
import type { LlmForm } from "./types";

type Props = {
  llmForm: LlmForm;
  setLlmForm: Dispatch<SetStateAction<LlmForm>>;
  presetDirty: boolean;
  saving: boolean;
  testing: boolean;
  capabilities: {
    max_tokens_limit: number | null;
    max_tokens_recommended: number | null;
    context_window_limit: number | null;
  } | null;
  onTestConnection: () => void;
  testConnectionDisabledReason?: string | null;
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

  apiKey: string;
  onChangeApiKey: (value: string) => void;
  onSaveApiKey: () => void;
  onClearApiKey: () => void;
};

function getJsonParseErrorPosition(message: string): number | null {
  const m = message.match(/\bposition\s+(\d+)\b/i);
  if (!m) return null;
  const pos = Number(m[1]);
  return Number.isFinite(pos) ? pos : null;
}

function getLineAndColumnFromPosition(text: string, position: number): { line: number; column: number } | null {
  if (!Number.isFinite(position) || position < 0 || position > text.length) return null;
  const before = text.slice(0, position);
  const parts = before.split(/\r?\n/);
  const line = parts.length;
  const column = parts[parts.length - 1].length + 1;
  return { line, column };
}

function validateExtraJson(
  raw: string,
): { ok: true; value: unknown } | { ok: false; message: string; position?: number; line?: number; column?: number } {
  const trimmed = (raw ?? "").trim();
  const effective = trimmed ? raw : "{}";
  try {
    return { ok: true, value: JSON.parse(effective) };
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    const position = getJsonParseErrorPosition(message);
    const lc = position !== null ? getLineAndColumnFromPosition(effective, position) : null;
    return {
      ok: false,
      message,
      ...(position !== null ? { position } : {}),
      ...(lc ? lc : {}),
    };
  }
}

export function LlmPresetPanel(props: Props) {
  const extraRaw = props.llmForm.extra;
  const setLlmForm = props.setLlmForm;

  const selectedProfile = props.selectedProfileId
    ? (props.profiles.find((p) => p.id === props.selectedProfileId) ?? null)
    : null;
  const testDisabledReason = (props.testConnectionDisabledReason ?? "").trim();

  const extraValidation = useMemo(() => validateExtraJson(extraRaw), [extraRaw]);
  const extraErrorText = extraValidation.ok
    ? ""
    : `extra JSON 无效${extraValidation.line ? `（第 ${extraValidation.line} 行，第 ${extraValidation.column ?? 1} 列）` : ""}：${extraValidation.message}`;

  const onFormatExtra = useCallback(() => {
    const parsed = validateExtraJson(extraRaw);
    if (!parsed.ok) return;
    setLlmForm((v) => ({
      ...v,
      extra: JSON.stringify(parsed.value, null, 2),
    }));
  }, [extraRaw, setLlmForm]);

  const maxTokensHint = (() => {
    if (!props.capabilities) return "";
    const parts: string[] = [];
    if (props.capabilities.max_tokens_recommended) parts.push(`推荐 ${props.capabilities.max_tokens_recommended}`);
    if (props.capabilities.max_tokens_limit) parts.push(`上限 ${props.capabilities.max_tokens_limit}`);
    if (props.capabilities.context_window_limit) parts.push(`上下文 ${props.capabilities.context_window_limit}`);
    return parts.join(" · ");
  })();

  return (
    <section className="panel p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="font-content text-xl">模型配置</div>
          <div className="mt-1 text-xs text-subtext">
            必填：服务商/接口地址/模型名（API Key 后端加密存储，不会回显明文）
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <div className="flex gap-2">
            <button
              className="btn btn-secondary"
              disabled={props.testing || props.profileBusy || Boolean(testDisabledReason) || !extraValidation.ok}
              onClick={props.onTestConnection}
              type="button"
            >
              {props.testing ? "测试中..." : "测试连接"}
            </button>
            <button
              className="btn btn-primary"
              disabled={!props.presetDirty || props.saving || !extraValidation.ok}
              onClick={props.onSave}
              type="button"
            >
              保存
            </button>
          </div>
          {testDisabledReason ? <div className="text-[11px] text-warning">{testDisabledReason}</div> : null}
          {extraErrorText ? <div className="text-[11px] text-warning">{extraErrorText}</div> : null}
        </div>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <label className="grid gap-1">
          <span className="text-xs text-subtext">服务商（provider）</span>
          <select
            className="select"
            name="provider"
            value={props.llmForm.provider}
            disabled={props.profileBusy}
            onChange={(e) =>
              props.setLlmForm((v) => ({
                ...v,
                provider: e.target.value as LLMProvider,
                max_tokens: "",
              }))
            }
          >
            <option value="openai">openai（官方）</option>
            <option value="openai_responses">openai_responses（官方 /v1/responses）</option>
            <option value="openai_compatible">openai_compatible（中转/本地）</option>
            <option value="openai_responses_compatible">openai_responses_compatible（中转/本地 /v1/responses）</option>
            <option value="anthropic">anthropic（Claude）</option>
            <option value="gemini">gemini</option>
          </select>
          <div className="text-[11px] text-subtext">
            openai_compatible：适用于本地 Mock/中转网关。不同服务商对 base_url 的格式要求不同，请按下方提示填写。
          </div>
        </label>
        <label className="grid gap-1">
          <span className="text-xs text-subtext">模型（model）</span>
          <input
            className="input"
            disabled={props.profileBusy}
            name="model"
            value={props.llmForm.model}
            onChange={(e) => props.setLlmForm((v) => ({ ...v, model: e.target.value }))}
          />
          <div className="text-[11px] text-subtext">填写服务端支持的模型名；报错时优先检查 model 是否拼写正确。</div>
        </label>

        <label className="grid gap-1 sm:col-span-2">
          <span className="text-xs text-subtext">接口地址（base_url）</span>
          <input
            className="input"
            placeholder={
              props.llmForm.provider === "openai_compatible" || props.llmForm.provider === "openai_responses_compatible"
                ? "https://your-proxy.com/v1"
                : undefined
            }
            disabled={props.profileBusy}
            name="base_url"
            value={props.llmForm.base_url}
            onChange={(e) => props.setLlmForm((v) => ({ ...v, base_url: e.target.value }))}
          />
          <div className="text-[11px] text-subtext">
            OpenAI-compatible 通常以 <span className="font-mono">/v1</span> 结尾；Anthropic/Gemini 通常填写 host（不带{" "}
            <span className="font-mono">/v1</span>）。
          </div>
        </label>
      </div>

      <details className="surface mt-4 p-4">
        <summary className="cursor-pointer select-none text-sm text-ink">高级参数（可选）</summary>
        <div className="mt-1 text-xs text-subtext">
          常见情况下保持默认即可；如需微调采样/停止词/超时/extra，可在此修改。
        </div>
        <div className="mt-3 grid gap-4 sm:grid-cols-3">
          <label className="grid gap-1">
            <span className="text-xs text-subtext">温度（temperature）</span>
            <input
              className="input"
              name="temperature"
              value={props.llmForm.temperature}
              onChange={(e) => props.setLlmForm((v) => ({ ...v, temperature: e.target.value }))}
            />
          </label>
          <label className="grid gap-1">
            <span className="text-xs text-subtext">top_p（核采样）</span>
            <input
              className="input"
              name="top_p"
              value={props.llmForm.top_p}
              onChange={(e) => props.setLlmForm((v) => ({ ...v, top_p: e.target.value }))}
            />
          </label>
          <label className="grid gap-1">
            <span className="text-xs text-subtext">最大输出（max_tokens）</span>
            <input
              className="input"
              name="max_tokens"
              value={props.llmForm.max_tokens}
              onChange={(e) => props.setLlmForm((v) => ({ ...v, max_tokens: e.target.value }))}
            />
            {maxTokensHint ? <div className="text-[11px] text-subtext">{maxTokensHint}</div> : null}
          </label>
          {props.llmForm.provider === "openai" || props.llmForm.provider === "openai_compatible" ? (
            <>
              <label className="grid gap-1">
                <span className="text-xs text-subtext">新颖度惩罚（presence_penalty）</span>
                <input
                  className="input"
                  name="presence_penalty"
                  value={props.llmForm.presence_penalty}
                  onChange={(e) => props.setLlmForm((v) => ({ ...v, presence_penalty: e.target.value }))}
                />
              </label>
              <label className="grid gap-1">
                <span className="text-xs text-subtext">重复惩罚（frequency_penalty）</span>
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
            <span className="text-xs text-subtext">停止词（stop，逗号分隔）</span>
            <input
              className="input"
              placeholder="---"
              name="stop"
              value={props.llmForm.stop}
              onChange={(e) => props.setLlmForm((v) => ({ ...v, stop: e.target.value }))}
            />
          </label>
          <label className="grid gap-1">
            <span className="text-xs text-subtext">超时（timeout_seconds，默认 180，最大 1800/30 分钟）</span>
            <input
              className="input"
              name="timeout_seconds"
              value={props.llmForm.timeout_seconds}
              onChange={(e) => props.setLlmForm((v) => ({ ...v, timeout_seconds: e.target.value }))}
            />
          </label>
          <label className="grid gap-1 sm:col-span-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs text-subtext">额外参数（extra，JSON）</span>
              <button
                className="btn btn-secondary btn-sm"
                disabled={props.profileBusy || !extraValidation.ok}
                onClick={onFormatExtra}
                type="button"
              >
                一键格式化
              </button>
            </div>
            <textarea
              className="textarea atelier-mono"
              name="extra"
              rows={5}
              value={props.llmForm.extra}
              onChange={(e) => props.setLlmForm((v) => ({ ...v, extra: e.target.value }))}
            />
            <div className="text-[11px] text-subtext">
              必须是合法 JSON。示例：<span className="font-mono">{'{"response_format":{"type":"json_object"}}'}</span>
              。不要在 extra 里填写 API Key。
            </div>
            {extraErrorText ? <div className="text-xs text-warning">{extraErrorText}</div> : null}
          </label>
        </div>
      </details>

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
