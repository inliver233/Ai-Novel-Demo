import { humanizeChapterStatus } from "../../lib/humanize";

const DRAFTING_LABEL = humanizeChapterStatus("drafting");
const DONE_LABEL = humanizeChapterStatus("done");

export const WRITING_PAGE_COPY = {
  loading: "加载中...",
  emptyState: "请选择或新建章节开始写作。",
  dirtyBadge: "（未保存）",
  updatedAtPrefix: "updated_at:",
  hotkeyHint: "快捷键：Ctrl/Cmd + S 保存",
  titleLabel: "标题",
  statusLabel: "状态",
  planLabel: "本章要点",
  contentLabel: "正文（Markdown）",
  contentPlaceholder: "开始写作...",
  summaryLabel: "摘要（可选）",
  analysis: "分析",
  trace: "标注回溯",
  delete: "删除",
  saveAndTrigger: "一键保存并触发更新",
  saveAndTriggerPending: "保存并触发中...",
  save: "保存",
  saving: "保存中...",
  openTaskCenter: "打开 TaskCenter",
  openChapterAnalysis: "打开标注页",
  switchedOutline: "已切换大纲",
  saveQueued: "保存中：已加入队列，将自动保存。",
  saveSuccess: "已保存",
  createSuccess: "已创建",
  deleteSuccess: "已删除",
  chapterNumberInvalid: "章号必须 >= 1",
  generateDoneUnsaved: "生成完成（别忘了保存）",
  generateEmptyStream: "未收到流式分片（可能上游未返回分片或输出为空）",
  generateFallback: "流式生成失败，已回退非流式",
  generateUnsupportedProviderFallback: "已回退非流式生成",
  generateCanceled: "已取消生成",
  generateFailed: "生成失败",
  applyRunSuccess: "已应用生成结果（别忘了保存）",
  applyRunEmpty: "生成记录为空，无法应用",
  autoUpdatesCreated: "已保存并创建无感更新任务",
  locateExcerptFailed: "未在正文中找到该引用片段（可复制后 Ctrl/Cmd+F 搜索）",
  memoryUpdateNeedsSaveFirst: "请先保存当前章节后再进行记忆更新。",
  promptPresetRequired: "请先在 Prompts 页保存 LLM 配置",
  analyzeEmptyContent: "正文为空，无法分析",
  analyzeDone: "分析完成",
  analyzeParseFailedPrefix: "分析解析失败：",
  analyzeInstructionDefault: "按分析建议重写，减少重复，保持叙事连续。",
  rewriteNeedsAnalysis: "请先完成章节分析",
  rewriteEmptyContent: "正文为空，无法重写",
  rewriteParseFailed: "重写解析失败",
  rewriteAppliedUnsaved: "已应用重写结果到编辑器（未保存）",
  saveAndGenerateLastChapter: "已保存，已是最后一章",
  streamFloatingTitle: "AI 流式生成中",
  streamFloatingPending: "处理中...",
  streamFloatingExpand: "展开",
  cancel: "取消",
  postEditRawApplied: "已采用原稿（别忘了保存）",
  postEditEditedApplied: "已采用后处理稿（别忘了保存）",
  contentOptimizeRawApplied: "已采用优化前原稿（别忘了保存）",
  contentOptimizeOptimizedApplied: "已采用正文优化稿（别忘了保存）",
  adoptionRecordFailedPrefix: "记录采用策略失败：",
  readonlyCalloutAction: `回退为 ${DRAFTING_LABEL} 并编辑`,
  confirms: {
    switchChapter: {
      title: "章节有未保存修改，是否切换？",
      description: "切换后未保存内容会丢失。",
      confirmText: "保存并切换",
      secondaryText: "不保存切换",
      cancelText: "取消",
    },
    switchOutline: {
      title: "章节有未保存修改，是否切换大纲？",
      description: "切换大纲后未保存内容会丢失。",
      confirmText: "保存并切换",
      secondaryText: "不保存切换",
      cancelText: "取消",
    },
    applyGenerationRun: {
      title: "章节有未保存修改，是否应用生成记录？",
      description: "应用后会覆盖编辑器内容（不会自动保存）。",
      confirmText: "保存并应用",
      secondaryText: "直接应用（不保存）",
      cancelText: "取消",
    },
    generateWithDirty: {
      title: "章节有未保存修改，如何生成？",
      description: "生成结果会写入编辑器，但不会自动保存。",
      confirmText: "保存并生成",
      secondaryText: "直接生成（不保存当前修改）",
      cancelText: "取消",
    },
    deleteChapter: {
      title: "删除章节？",
      description: "删除后该章节正文与摘要将丢失。",
      confirmText: "删除",
    },
    nextChapterReplace: {
      description: "将以“替换”模式生成草稿（生成结果不会自动保存）。",
      confirmText: "继续",
      cancelText: "取消",
    },
  },
} as const;

export function getWritingChapterHeading(chapterNumber: number): string {
  return `第 ${chapterNumber} 章`;
}

export function getWritingReadonlyCallout(): string {
  return `本章已定稿：为避免误操作，编辑区默认只读。如需修改，请先回退为 ${DRAFTING_LABEL}。`;
}

export function getWritingStatusHint(): string {
  return `提示：保存不等于定稿。仅状态为 ${DONE_LABEL} 的章节允许进行记忆更新（Memory Update）写入长期记忆；定稿章默认只读，修改请先切回 ${DRAFTING_LABEL}。`;
}

export function getWritingDoneOnlyWarning(): string {
  return `仅状态为 ${DONE_LABEL} 的章节允许记忆更新；请先将章节标记为 ${DONE_LABEL}。`;
}

export function getWritingAnalysisHref(projectId: string, chapterId: string): string {
  return `/projects/${projectId}/chapter-analysis?chapterId=${chapterId}`;
}

export function getWritingNextChapterReplaceTitle(chapterNumber: number): string {
  return `下一章（第 ${chapterNumber} 章）已有内容，仍要开始生成？`;
}

export function getWritingGenerateIndicatorLabel(message?: string, progress?: number): string {
  if (!message) return "墨迹渗入纸张中…生成需要一点时间";
  return `${message}（${Math.max(0, Math.min(100, progress ?? 0))}%）`;
}

export function getWritingMissingPrerequisiteMessage(numbers: number[]): string {
  return `缺少前置章节内容：第 ${numbers.join("、")} 章`;
}

export function getWritingJumpToChapterLabel(chapterNumber: number): string {
  return `跳转到第 ${chapterNumber} 章`;
}

export function getWritingApplyMemorySuccess(count: number): string {
  return `已生成 ${count} 条记忆（标注可用）`;
}
