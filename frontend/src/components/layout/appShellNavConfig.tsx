import type { LucideIcon } from "lucide-react";
import {
  Bot,
  BookOpen,
  BookOpenText,
  BookText,
  Database,
  FileDown,
  Flag,
  Globe,
  ListTodo,
  Palette,
  PenLine,
  Share2,
  Settings,
  Snowflake,
  Sparkles,
  TableOfContents,
  Table2,
  Users,
} from "lucide-react";

import { UI_COPY } from "../../lib/uiCopy";

export type AppShellProjectNavGroup = "workbench" | "view" | "aiConfig" | "advancedDebug";

export type AppShellProjectNavItem = {
  id: string;
  group: AppShellProjectNavGroup;
  icon: LucideIcon;
  label: string;
  ariaLabel: string;
  to: (projectId: string) => string;
};

export const APP_SHELL_PRIMARY_PROJECT_NAV_GROUPS: AppShellProjectNavGroup[] = ["workbench", "view", "aiConfig"];
export const APP_SHELL_ADVANCED_DEBUG_PROJECT_NAV_GROUP: AppShellProjectNavGroup = "advancedDebug";

export const APP_SHELL_PROJECT_NAV_GROUP_TITLES: Record<AppShellProjectNavGroup, string> = {
  workbench: UI_COPY.nav.groupWorkbench,
  view: UI_COPY.nav.groupView,
  aiConfig: UI_COPY.nav.groupAiConfig,
  advancedDebug: UI_COPY.nav.groupAdvancedDebug,
};

export const APP_SHELL_PROJECT_NAV_ITEMS: ReadonlyArray<AppShellProjectNavItem> = [
  {
    id: "writing",
    group: "workbench",
    icon: PenLine,
    label: UI_COPY.nav.writing,
    ariaLabel: "写作 (nav_writing)",
    to: (projectId) => `/projects/${projectId}/writing`,
  },
  {
    id: "outline",
    group: "workbench",
    icon: TableOfContents,
    label: UI_COPY.nav.outline,
    ariaLabel: "大纲 (nav_outline)",
    to: (projectId) => `/projects/${projectId}/outline`,
  },
  {
    id: "characters",
    group: "workbench",
    icon: Users,
    label: UI_COPY.nav.characters,
    ariaLabel: "角色卡 (nav_characters)",
    to: (projectId) => `/projects/${projectId}/characters`,
  },
  {
    id: "worldbook",
    group: "workbench",
    icon: Globe,
    label: UI_COPY.nav.worldBook,
    ariaLabel: "世界书 (nav_worldbook)",
    to: (projectId) => `/projects/${projectId}/worldbook`,
  },
  {
    id: "graph",
    group: "workbench",
    icon: Share2,
    label: UI_COPY.nav.graph,
    ariaLabel: "图谱/关系 (nav_graph)",
    to: (projectId) => `/projects/${projectId}/graph`,
  },
  {
    id: "numericTables",
    group: "workbench",
    icon: Table2,
    label: UI_COPY.nav.numericTables,
    ariaLabel: "数值表格（NumericTables） (nav_numeric_tables)",
    to: (projectId) => `/projects/${projectId}/numeric-tables`,
  },
  {
    id: "chapterAnalysis",
    group: "view",
    icon: BookText,
    label: UI_COPY.nav.chapterAnalysis,
    ariaLabel: "剧情记忆 (nav_chapter_analysis)",
    to: (projectId) => `/projects/${projectId}/chapter-analysis`,
  },
  {
    id: "preview",
    group: "view",
    icon: BookOpen,
    label: UI_COPY.nav.preview,
    ariaLabel: "预览 (nav_preview)",
    to: (projectId) => `/projects/${projectId}/preview`,
  },
  {
    id: "foreshadows",
    group: "view",
    icon: Flag,
    label: UI_COPY.nav.foreshadows,
    ariaLabel: "伏笔 (nav_foreshadows)",
    to: (projectId) => `/projects/${projectId}/foreshadows`,
  },
  {
    id: "reader",
    group: "view",
    icon: BookOpenText,
    label: UI_COPY.nav.reader,
    ariaLabel: "阅读 (nav_reader)",
    to: (projectId) => `/projects/${projectId}/reader`,
  },
  {
    id: "export",
    group: "view",
    icon: FileDown,
    label: UI_COPY.nav.export,
    ariaLabel: "导出 (nav_export)",
    to: (projectId) => `/projects/${projectId}/export`,
  },
  {
    id: "prompts",
    group: "aiConfig",
    icon: Bot,
    label: UI_COPY.nav.prompts,
    ariaLabel: "模型配置 (nav_prompts)",
    to: (projectId) => `/projects/${projectId}/prompts`,
  },
  {
    id: "promptStudio",
    group: "aiConfig",
    icon: Sparkles,
    label: UI_COPY.nav.promptStudio,
    ariaLabel: "提示词工作室 (nav_prompt_studio)",
    to: (projectId) => `/projects/${projectId}/prompt-studio`,
  },
  {
    id: "styles",
    group: "aiConfig",
    icon: Palette,
    label: UI_COPY.nav.styles,
    ariaLabel: "风格 (nav_styles)",
    to: (projectId) => `/projects/${projectId}/styles`,
  },
  {
    id: "settings",
    group: "aiConfig",
    icon: Settings,
    label: UI_COPY.nav.projectSettings,
    ariaLabel: "项目设置 (nav_settings)",
    to: (projectId) => `/projects/${projectId}/settings`,
  },
  {
    id: "rag",
    group: "advancedDebug",
    icon: Database,
    label: UI_COPY.nav.rag,
    ariaLabel: "知识库（RAG） (nav_rag)",
    to: (projectId) => `/projects/${projectId}/rag`,
  },
  {
    id: "search",
    group: "advancedDebug",
    icon: BookText,
    label: UI_COPY.nav.search,
    ariaLabel: "搜索引擎 (nav_search)",
    to: (projectId) => `/projects/${projectId}/search`,
  },
  {
    id: "fractal",
    group: "advancedDebug",
    icon: Snowflake,
    label: UI_COPY.nav.fractal,
    ariaLabel: "分形（Fractal） (nav_fractal)",
    to: (projectId) => `/projects/${projectId}/fractal`,
  },
  {
    id: "structuredMemory",
    group: "advancedDebug",
    icon: Table2,
    label: UI_COPY.nav.structuredMemory,
    ariaLabel: "图谱底座数据 (nav_structured_memory)",
    to: (projectId) => `/projects/${projectId}/structured-memory`,
  },
  {
    id: "tasks",
    group: "advancedDebug",
    icon: ListTodo,
    label: UI_COPY.nav.tasks,
    ariaLabel: "任务中心 (nav_tasks)",
    to: (projectId) => `/projects/${projectId}/tasks`,
  },
];

export function getAppShellProjectNavItems(group: AppShellProjectNavGroup): AppShellProjectNavItem[] {
  return APP_SHELL_PROJECT_NAV_ITEMS.filter((item) => item.group === group);
}
