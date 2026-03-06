import { apiJson } from "./apiClient";
import type { Chapter, ChapterListItem, ChapterMetaPage } from "../types";

type FetchChapterMetaOptions = {
  outlineId?: string | null;
  cursor?: string | null;
  limit?: number;
};

function buildMetaQuery(options: FetchChapterMetaOptions): string {
  const params = new URLSearchParams();
  if (typeof options.limit === "number" && Number.isFinite(options.limit) && options.limit > 0) {
    params.set("limit", String(Math.floor(options.limit)));
  }
  if (options.cursor) params.set("cursor", options.cursor);
  if (options.outlineId) params.set("outline_id", options.outlineId);
  const query = params.toString();
  return query ? `?${query}` : "";
}

function hasText(value: string | null | undefined): boolean {
  return Boolean(value && value.trim());
}

export function chapterDetailToListItem(chapter: Chapter): ChapterListItem {
  return {
    ...chapter,
    has_plan: hasText(chapter.plan),
    has_summary: hasText(chapter.summary),
    has_content: hasText(chapter.content_md),
  };
}

export async function fetchChapterMetaPage(
  projectId: string,
  options: FetchChapterMetaOptions = {},
): Promise<ChapterMetaPage> {
  const res = await apiJson<ChapterMetaPage>(`/api/projects/${projectId}/chapters/meta${buildMetaQuery(options)}`);
  return res.data;
}

export async function fetchAllChapterMeta(
  projectId: string,
  options: Omit<FetchChapterMetaOptions, "cursor"> = {},
): Promise<ChapterListItem[]> {
  const chapters: ChapterListItem[] = [];
  let cursor: string | null = null;
  let pageCount = 0;

  while (pageCount < 50) {
    const page = await fetchChapterMetaPage(projectId, { ...options, cursor });
    chapters.push(...(page.chapters ?? []));
    if (!page.has_more || !page.next_cursor) break;
    cursor = page.next_cursor;
    pageCount += 1;
  }

  return chapters.sort((a, b) => (a.number ?? 0) - (b.number ?? 0));
}

export async function fetchChapterDetail(chapterId: string): Promise<Chapter> {
  const res = await apiJson<{ chapter: Chapter }>(`/api/chapters/${chapterId}`);
  return res.data.chapter;
}
