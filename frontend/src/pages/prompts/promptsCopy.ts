export const PROMPTS_COPY = {
  vectorRag: {
    saveBeforeTestToast: "请先保存 RAG 配置后再测试（测试使用已保存配置）",
    saveBeforeTestHint: "提示：测试使用已保存配置；请先点“保存 RAG 配置”。",
  },
  confirm: {
    deleteProfile: {
      title: "删除当前后端配置？",
      description: "删除后不可恢复。项目将解除绑定，需要重新选择/新建配置并保存 Key。",
      confirmText: "删除",
    },
    clearProfileApiKey: {
      title: "清除 API Key？",
      description: "清除后将无法生成/测试连接，直到重新保存 Key。",
      confirmText: "清除",
    },
  },
} as const;

export function buildDeleteTaskModuleConfirm(taskLabel: string) {
  return {
    title: "删除任务模块",
    description: `确认删除任务模块「${taskLabel}」？删除后将回退到主模块。`,
    confirmText: "删除",
    cancelText: "取消",
  } as const;
}

export function buildClearTaskApiKeyConfirm(profileName: string) {
  return {
    title: "清除任务模块绑定配置的 API Key？",
    description: `将清除配置库「${profileName}」的 Key。该配置库被其他模块复用时也会立即失效。`,
    confirmText: "清除",
    cancelText: "取消",
  } as const;
}
