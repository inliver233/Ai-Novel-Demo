export function formatBinaryStatus(enabled: boolean): "enabled" | "disabled" {
  return enabled ? "enabled" : "disabled";
}

export const SETTINGS_COPY = {
  featureDefaults: {
    status: (enabled: boolean) => `status: memory_injection_default=${formatBinaryStatus(enabled)} (localStorage)`,
  },
  contextOptimizer: {
    status: (enabled: boolean) => `status: ${formatBinaryStatus(enabled)}`,
  },
  queryPreprocess: {
    ariaLabel: "Query 预处理（Query Preprocessing）",
    title: "Query 预处理（Query Preprocessing）",
    subtitle: "用于把 query_text 先“标准化/去噪”，让 WorldBook / Vector RAG / Graph 的检索更稳定（默认关闭）。",
    featureHint: "功能：提取 #tag、移除 exclusion_rules、可选识别章节引用（index_ref_enhance）。",
    enableLabel: "启用 query_preprocessing（默认关闭）",
    tagsLabel: "tags（每行一条；匹配 #tag；留空=提取所有 tag）",
    tagsHint: "最大 50 条；每条最多 64 字符。",
    exclusionRulesLabel: "exclusion_rules（每行一条；出现则移除）",
    exclusionRulesHint: "最大 50 条；每条最多 256 字符。",
    indexRefEnhanceLabel: "index_ref_enhance（识别“第N章 / chapter N”并追加引用 token）",
    previewTitle: "示例 normalize（基于已保存的 effective 配置）",
    previewHint: "修改配置后请先保存，再点击预览。",
    previewPlaceholder: "例如：回顾第1章 #foo REMOVE",
    previewButton: "预览",
    previewLoadingButton: "预览中…",
    clearResultButton: "清空结果",
    emptyState: "启用后可配置 tags / exclusion_rules，并可在下方预览 normalized_query_text（保存后生效）。",
  },
  vectorRag: {
    openPromptsConfigHint:
      "配置入口已迁移到「模型配置」页（向量检索）。建议在那边完成 Embedding/Rerank 配置后再回到这里查看生效状态。",
    openPromptsConfigCta: "打开模型配置",
    saveBeforeTestToast: "请先保存设置后再测试（测试使用已保存配置）",
    saveBeforeTestHint: "提示：测试使用已保存配置；请先保存当前设置。",
  },
} as const;
