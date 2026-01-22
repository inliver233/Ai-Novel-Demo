import type { Character, Outline, Project, ProjectSettings } from "../../types";

const TRIGGER_TOKEN_RE = /^[a-z][a-z0-9_]*$/;

export function formatTriggers(value: string[]): string {
  return (value ?? []).join(", ");
}

export function parseTriggersWithValidation(value: string): { triggers: string[]; invalid: string[] } {
  const trimmed = value.trim();
  if (!trimmed) return { triggers: [], invalid: [] };

  const raw = trimmed
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const seen = new Set<string>();
  const invalidSet = new Set<string>();
  const triggers: string[] = [];

  for (const item of raw) {
    if (!TRIGGER_TOKEN_RE.test(item) || item.length > 64) invalidSet.add(item);
    if (seen.has(item)) continue;
    seen.add(item);
    triggers.push(item);
  }
  return { triggers, invalid: [...invalidSet] };
}

function formatCharacters(chars: Character[]): string {
  return chars.map((c) => `- ${c.name}${c.role ? `（${c.role}）` : ""}`).join("\n");
}

export function guessPreviewValues(args: {
  project: Project | null;
  settings: ProjectSettings | null;
  outline: Outline | null;
  characters: Character[];
}): Record<string, unknown> {
  const projectName = args.project?.name ?? "";
  const genre = args.project?.genre ?? "";
  const logline = args.project?.logline ?? "";
  const worldSetting = args.settings?.world_setting ?? "";
  const styleGuide = args.settings?.style_guide ?? "";
  const constraints = args.settings?.constraints ?? "";
  const charactersText = formatCharacters(args.characters);
  const outlineText = args.outline?.content_md ?? "";

  const chapterNumber = 1;
  const chapterTitle = "第一章";
  const chapterPlan = "（示例要点）";
  const chapterSummary = "（示例摘要）";
  const instruction = "（示例指令）";
  const previousChapter = "（示例上一章摘要）";
  const targetWordCount = 2500;
  const rawContent = "（示例已生成正文，用于 post_edit 预览）";
  const chapterContentMd = "（示例章节正文，用于 chapter_analyze / chapter_rewrite）";
  const planText = "（示例规划，可用于 plan_first 注入）";
  const analysisJson = JSON.stringify(
    {
      chapter_summary: "（示例分析摘要）",
      hooks: [{ excerpt: "（示例 excerpt）", note: "（示例 hook 备注）" }],
      foreshadows: [],
      plot_points: [{ beat: "（示例情节点）", excerpt: "（示例 excerpt）" }],
      suggestions: [
        {
          title: "（示例建议）",
          excerpt: "（示例 excerpt）",
          issue: "（示例问题）",
          recommendation: "（示例建议）",
          priority: "medium",
        },
      ],
      overall_notes: "",
    },
    null,
    2,
  );
  const requirementsObj = { chapter_count: 12 };

  const values: Record<string, unknown> = {
    project_name: projectName,
    genre,
    logline,
    world_setting: worldSetting,
    style_guide: styleGuide,
    constraints,
    characters: charactersText,
    outline: outlineText,
    chapter_number: String(chapterNumber),
    chapter_title: chapterTitle,
    chapter_plan: chapterPlan,
    chapter_summary: chapterSummary,
    chapter_content_md: chapterContentMd,
    analysis_json: analysisJson,
    requirements: JSON.stringify(requirementsObj, null, 2),
    instruction,
    previous_chapter: previousChapter,
    target_word_count: String(targetWordCount),
    raw_content: rawContent,
    story_plan: planText,
    smart_context_recent_summaries: "（示例 smart_context_recent_summaries）",
    smart_context_recent_full: "（示例 smart_context_recent_full）",
    smart_context_story_skeleton: "（示例 smart_context_story_skeleton）",
  };
  values.project = {
    name: projectName,
    genre,
    logline,
    world_setting: worldSetting,
    style_guide: styleGuide,
    constraints,
    characters: charactersText,
  };
  values.story = {
    outline: outlineText,
    chapter_number: chapterNumber,
    chapter_title: chapterTitle,
    chapter_plan: chapterPlan,
    chapter_summary: chapterSummary,
    previous_chapter: previousChapter,
    plan: planText,
    raw_content: rawContent,
    chapter_content_md: chapterContentMd,
    analysis_json: analysisJson,
    smart_context_recent_summaries: "（示例 smart_context_recent_summaries）",
    smart_context_recent_full: "（示例 smart_context_recent_full）",
    smart_context_story_skeleton: "（示例 smart_context_story_skeleton）",
  };
  values.user = { instruction, requirements: requirementsObj };

  return values;
}
