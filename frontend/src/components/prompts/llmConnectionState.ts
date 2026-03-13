import type { LLMProfile, LLMProvider } from "../../types";

import type { LlmModelListState } from "./types";

export type LlmModuleAccessStage = "missing_profile" | "missing_key" | "provider_mismatch" | "ready";

export type LlmModuleAccessState = {
  stage: LlmModuleAccessStage;
  tone: "warning" | "success";
  title: string;
  detail: string;
  actionReason: string | null;
  effectiveProfile: LLMProfile | null;
};

type DeriveOptions = {
  scope: "main" | "task";
  moduleProvider: LLMProvider;
  selectedProfile: LLMProfile | null;
  boundProfile?: LLMProfile | null;
};

function profileSummary(profile: LLMProfile): string {
  const masked = profile.masked_api_key ? `，Key：${profile.masked_api_key}` : "";
  return `profile「${profile.name}」(${profile.provider}/${profile.model}${masked})`;
}

function createBlockedState(
  stage: Exclude<LlmModuleAccessStage, "ready">,
  title: string,
  detail: string,
  actionReason: string,
  effectiveProfile: LLMProfile | null = null,
): LlmModuleAccessState {
  return {
    stage,
    tone: "warning",
    title,
    detail,
    actionReason,
    effectiveProfile,
  };
}

export function deriveLlmModuleAccessState(options: DeriveOptions): LlmModuleAccessState {
  const boundProfile = options.boundProfile ?? null;
  const effectiveProfile = boundProfile ?? options.selectedProfile ?? null;
  const usingFallback = options.scope === "task" && !boundProfile;
  const sourceLabel = boundProfile ? "任务绑定 profile" : usingFallback ? "主模块回退 profile" : "主模块 profile";

  if (!effectiveProfile) {
    return createBlockedState(
      "missing_profile",
      "远程状态：未绑定 profile",
      options.scope === "task"
        ? "当前任务既没有绑定独立 profile，也没有可回退的主模块 profile。先绑定 profile，再保存 API Key。"
        : "当前主模块还没有绑定 profile（API 配置库）。先选择或新建 profile，再保存 API Key。",
      options.scope === "task" ? "请先为该任务绑定 profile，或先设置主模块 profile。" : "请先绑定主模块 profile。",
    );
  }

  if (effectiveProfile.provider !== options.moduleProvider) {
    return createBlockedState(
      "provider_mismatch",
      "远程状态：provider 不匹配",
      `当前模块 provider = ${options.moduleProvider}，${sourceLabel} provider = ${effectiveProfile.provider}。先让两者一致，再拉取模型列表或测试连接。`,
      `${sourceLabel} 与当前模块 provider 不一致。`,
      effectiveProfile,
    );
  }

  if (!effectiveProfile.has_api_key) {
    return createBlockedState(
      "missing_key",
      "远程状态：已绑定 profile，但未保存 Key",
      `${sourceLabel} 已绑定，但还没有保存 API Key。保存 Key 后才能拉取模型列表或测试连接。`,
      `${sourceLabel} 还没有保存 API Key。`,
      effectiveProfile,
    );
  }

  return {
    stage: "ready",
    tone: "success",
    title: "远程状态：可请求远端",
    detail: `${sourceLabel} 已就绪：${profileSummary(effectiveProfile)}。现在可以拉取模型列表，也可以测试连接。`,
    actionReason: null,
    effectiveProfile,
  };
}

export function describeModelListState(modelList: LlmModelListState, accessState: LlmModuleAccessState): string {
  if (accessState.actionReason) return `当前不可拉取模型列表：${accessState.actionReason}`;
  if (modelList.loading) return "正在根据当前 provider 和 base_url 拉取模型列表…";
  if (modelList.error) return `拉取失败：${modelList.error}。仍可手动输入 model。`;
  if (modelList.warning) return `远端返回提醒：${modelList.warning}。仍可手动输入 model。`;
  if (modelList.options.length > 0) {
    return `已拉取 ${modelList.options.length} 个候选模型；可下拉选择，也可手动输入 model。`;
  }
  if (modelList.requestId) {
    return "已请求远端，但没有返回候选模型；请检查 provider/base_url，或直接手动输入 model。";
  }
  return "支持“拉取模型列表 + 手动输入 model”两种方式。";
}
