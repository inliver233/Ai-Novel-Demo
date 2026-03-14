export const WRITING_RUNTIME_COPY = {
  promptOverrideWarning: "已启用 Prompt 覆盖：生成将使用覆盖文本（可随时回退默认）。",
  promptOverridePersistenceHint: "提示：使用覆盖后，“生成/追加生成”也会继续沿用覆盖文本，直到回退默认。",
  bundlePrivacyHint: "提示：可能包含隐私/敏感内容，分享前请确认并避免公开传播",
  bundleSafetyHint: "安全：按设计不应包含 API Key；分享前仍建议自行快速检索",
  previewBundleSafetyHint: "可用“下载预览 bundle”导出排障材料；按设计不应包含 API Key（分享前仍建议自行快速检索）",
  bundleExportRecommendation: "建议优先用顶部「下载预览 bundle」导出文件。需要复制粘贴时，可用下方按钮。",
  loadFailed: "加载失败",
  disabledLabel: "disabled",
  unknownLabel: "unknown",
} as const;

export function formatWritingDisabledReason(reason: string | null | undefined) {
  return `${WRITING_RUNTIME_COPY.disabledLabel}: ${reason ?? WRITING_RUNTIME_COPY.unknownLabel}`;
}
