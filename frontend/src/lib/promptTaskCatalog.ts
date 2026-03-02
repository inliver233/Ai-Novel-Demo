import type { PromptStudioTask } from "../pages/promptStudio/types";
import { UI_COPY } from "./uiCopy";

export const PROMPT_TASK_CATALOG = [
  {
    key: "outline_generate",
    uiCopyKey: "outlineGenerate",
    label: UI_COPY.promptStudio.tasks.outlineGenerate,
  },
  {
    key: "chapter_generate",
    uiCopyKey: "chapterGenerate",
    label: UI_COPY.promptStudio.tasks.chapterGenerate,
  },
  {
    key: "plan_chapter",
    uiCopyKey: "planChapter",
    label: UI_COPY.promptStudio.tasks.planChapter,
  },
  {
    key: "post_edit",
    uiCopyKey: "postEdit",
    label: UI_COPY.promptStudio.tasks.postEdit,
  },
  {
    key: "content_optimize",
    uiCopyKey: "contentOptimize",
    label: UI_COPY.promptStudio.tasks.contentOptimize,
  },
  {
    key: "chapter_analyze",
    uiCopyKey: "chapterAnalyze",
    label: UI_COPY.promptStudio.tasks.chapterAnalyze,
  },
  {
    key: "chapter_rewrite",
    uiCopyKey: "chapterRewrite",
    label: UI_COPY.promptStudio.tasks.chapterRewrite,
  },
] as const satisfies ReadonlyArray<{
  key: string;
  uiCopyKey: keyof typeof UI_COPY.promptStudio.tasks;
  label: string;
}>;

export const PROMPT_STUDIO_TASKS: PromptStudioTask[] = PROMPT_TASK_CATALOG.map((item) => ({
  key: item.key,
  label: item.label,
}));

export const PROMPT_TASK_KEYS = PROMPT_STUDIO_TASKS.map((item) => item.key);
