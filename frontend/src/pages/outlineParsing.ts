export type OutlineGenChapter = { number: number; title: string; beats: string[] };
export type OutlineGenResult = {
  outline_md: string;
  chapters: OutlineGenChapter[];
  raw_output: string;
  parse_error?: { code: string; message: string };
};

export function extractOutlineChapters(structure: unknown): OutlineGenChapter[] {
  if (!structure || typeof structure !== "object") return [];
  const maybe = structure as { chapters?: unknown };
  if (!Array.isArray(maybe.chapters)) return [];
  return maybe.chapters
    .map((item) => {
      const raw = item as { number?: unknown; title?: unknown; beats?: unknown };
      const number = typeof raw.number === "number" ? raw.number : Number(raw.number);
      if (!Number.isFinite(number) || number <= 0) return null;
      const title = typeof raw.title === "string" ? raw.title : "";
      const beats = Array.isArray(raw.beats) ? raw.beats.map((b) => String(b)).filter(Boolean) : [];
      return { number, title, beats } satisfies OutlineGenChapter;
    })
    .filter((v): v is OutlineGenChapter => Boolean(v));
}

export function normalizeOutlineGenResult(raw: unknown, fallbackRawOutput = ""): OutlineGenResult | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as {
    outline_md?: unknown;
    chapters?: unknown;
    raw_output?: unknown;
    parse_error?: unknown;
  };
  const outline_md = typeof data.outline_md === "string" ? data.outline_md : "";
  const chapters = extractOutlineChapters({ chapters: data.chapters });
  const raw_output = typeof data.raw_output === "string" ? data.raw_output : fallbackRawOutput;
  const parse_error =
    data.parse_error && typeof data.parse_error === "object"
      ? {
          code: String((data.parse_error as { code?: unknown }).code ?? ""),
          message: String((data.parse_error as { message?: unknown }).message ?? ""),
        }
      : undefined;
  if (!outline_md && chapters.length === 0 && !raw_output) return null;
  return { outline_md, chapters, raw_output, parse_error };
}

export function parseOutlineGenResultFromText(text: string): OutlineGenResult | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  const candidates: string[] = [trimmed];
  const firstBrace = trimmed.indexOf("{");
  const lastBrace = trimmed.lastIndexOf("}");
  if (firstBrace >= 0 && lastBrace > firstBrace) {
    candidates.push(trimmed.slice(firstBrace, lastBrace + 1));
  }
  for (const candidate of candidates) {
    try {
      const parsed = JSON.parse(candidate) as unknown;
      const normalized = normalizeOutlineGenResult(parsed, text);
      if (normalized) return normalized;
    } catch {
      // ignore and continue fallback parsing
    }
  }
  return null;
}

export function deriveOutlineFromStoredContent(
  contentMd: string,
  structure: unknown,
): {
  normalizedContentMd: string;
  chapters: OutlineGenChapter[];
} {
  const storedChapters = extractOutlineChapters(structure);
  if (storedChapters.length > 0) {
    return { normalizedContentMd: contentMd, chapters: storedChapters };
  }
  const parsed = parseOutlineGenResultFromText(contentMd);
  if (parsed && parsed.chapters.length > 0) {
    return {
      normalizedContentMd: parsed.outline_md || contentMd,
      chapters: parsed.chapters,
    };
  }
  return { normalizedContentMd: contentMd, chapters: [] };
}
