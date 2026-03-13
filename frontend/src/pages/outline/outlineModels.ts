import type { OutlineGenResult } from "../outlineParsing";

export type OutlineGenForm = {
  chapter_count: number;
  tone: string;
  pacing: string;
  include_world_setting: boolean;
  include_characters: boolean;
};

export type OutlineStreamProgress = {
  message: string;
  progress: number;
  status: string;
};

export const DEFAULT_OUTLINE_GEN_FORM: OutlineGenForm = {
  chapter_count: 12,
  tone: "偏现实，克制但有爆点",
  pacing: "前3章强钩子，中段升级，结尾反转",
  include_world_setting: true,
  include_characters: true,
};

export const STREAM_RAW_MAX_CHARS = 36000;
const STREAM_RAW_PREFIX_RE = /^\[raw 已截断前 (\d+) 字符，仅保留最近 \d+ 字符\]\n/;

export function toFinalPreviewJson(result: OutlineGenResult): string {
  return JSON.stringify(
    {
      outline_md: result.outline_md,
      chapters: result.chapters,
      parse_error: result.parse_error ?? undefined,
    },
    null,
    2,
  );
}

export function appendCappedRawText(prev: string, chunk: string, maxChars = STREAM_RAW_MAX_CHARS): string {
  if (!chunk) return prev;
  const previousMatch = prev.match(STREAM_RAW_PREFIX_RE);
  const previousOmitted = previousMatch ? Number(previousMatch[1] ?? 0) : 0;
  const previousBody = prev.replace(STREAM_RAW_PREFIX_RE, "");
  const merged = `${previousBody}${chunk}`;
  if (merged.length <= maxChars) return merged;
  const omitted = previousOmitted + merged.length - maxChars;
  return `[raw 已截断前 ${omitted} 字符，仅保留最近 ${maxChars} 字符]\n${merged.slice(-maxChars)}`;
}

export function waitMs(ms: number): Promise<void> {
  return new Promise((resolve) => {
    globalThis.setTimeout(resolve, ms);
  });
}

export function buildNextOutlineTitle(outlineCount: number): string {
  return `大纲 v${Math.max(1, outlineCount + 1)}`;
}

export function buildGeneratedOutlineTitle(now = new Date()): string {
  return `AI 大纲 ${now.toISOString().slice(0, 16).replace("T", " ")}`;
}
