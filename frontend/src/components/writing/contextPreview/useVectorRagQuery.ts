import { useCallback, useEffect, useMemo, useState } from "react";

import { UI_COPY } from "../../../lib/uiCopy";
import { ApiError, apiJson } from "../../../services/apiClient";

import type { VectorSource, VectorRagQueryResult } from "./vectorRag";
import { normalizeVectorResult } from "./vectorRag";

type ToastApi = {
  toastError: (message: string, requestId?: string) => void;
};

export type VectorRagQueryError = { code: string; message: string; requestId?: string };

export type GroupedVectorFinalChunks = Array<{
  source: string;
  chapterGroups: Array<{
    key: string;
    sourceId: string;
    title: string;
    chapterNumber: number | null;
    chunks: Array<{
      id: string;
      distance: number | null;
      text: string;
      source: string;
      sourceId: string;
      title: string;
      chapterNumber: number | null;
      chunkIndex: number;
      metadata: Record<string, unknown>;
    }>;
  }>;
}>;

export function useVectorRagQuery(params: { open: boolean; projectId?: string; toast: ToastApi }) {
  const { open, projectId, toast } = params;

  const [vectorQueryText, setVectorQueryText] = useState("");
  const [vectorSources, setVectorSources] = useState<Record<VectorSource, boolean>>({
    worldbook: true,
    outline: true,
    chapter: true,
  });
  const selectedVectorSources = useMemo(() => {
    const out: VectorSource[] = [];
    for (const src of ["worldbook", "outline", "chapter"] as const) {
      if (vectorSources[src]) out.push(src);
    }
    return out;
  }, [vectorSources]);

  const [vectorLoading, setVectorLoading] = useState(false);
  const [vectorResult, setVectorResult] = useState<VectorRagQueryResult | null>(null);
  const [vectorRequestId, setVectorRequestId] = useState<string | null>(null);
  const [vectorRawQueryText, setVectorRawQueryText] = useState<string | null>(null);
  const [vectorNormalizedQueryText, setVectorNormalizedQueryText] = useState<string | null>(null);
  const [vectorPreprocessObs, setVectorPreprocessObs] = useState<unknown>(null);
  const [vectorError, setVectorError] = useState<VectorRagQueryError | null>(null);

  const groupedVectorFinalChunks: GroupedVectorFinalChunks = useMemo(() => {
    type GroupChunk = {
      id: string;
      distance: number | null;
      text: string;
      source: string;
      sourceId: string;
      title: string;
      chapterNumber: number | null;
      chunkIndex: number;
      metadata: Record<string, unknown>;
    };

    type ChapterGroup = {
      key: string;
      sourceId: string;
      title: string;
      chapterNumber: number | null;
      chunks: GroupChunk[];
    };

    const chunks = vectorResult?.final?.chunks ?? [];
    const bySource = new Map<string, Map<string, ChapterGroup>>();

    for (const raw of chunks) {
      const meta = (raw.metadata ?? {}) as Record<string, unknown>;
      const source = typeof meta.source === "string" ? meta.source : "unknown";
      const sourceId = typeof meta.source_id === "string" ? meta.source_id : "";
      const title = typeof meta.title === "string" ? meta.title : "";
      const chapterRaw = meta.chapter_number;
      const chapterNumber = typeof chapterRaw === "number" ? chapterRaw : Number(chapterRaw);
      const chapter = Number.isFinite(chapterNumber) ? chapterNumber : null;
      const chunkRaw = meta.chunk_index;
      const chunkIndex = typeof chunkRaw === "number" ? chunkRaw : Number(chunkRaw);
      const idx = Number.isFinite(chunkIndex) ? chunkIndex : 0;

      const groupKey = `${chapter ?? "-"}::${sourceId || title || raw.id}`;
      const chunk: GroupChunk = {
        id: raw.id,
        distance: typeof raw.distance === "number" && Number.isFinite(raw.distance) ? raw.distance : null,
        text: String(raw.text ?? ""),
        source,
        sourceId,
        title,
        chapterNumber: chapter,
        chunkIndex: idx,
        metadata: meta,
      };

      let sourceMap = bySource.get(source);
      if (!sourceMap) {
        sourceMap = new Map<string, ChapterGroup>();
        bySource.set(source, sourceMap);
      }
      let chapterGroup = sourceMap.get(groupKey);
      if (!chapterGroup) {
        chapterGroup = { key: groupKey, sourceId, title, chapterNumber: chapter, chunks: [] };
        sourceMap.set(groupKey, chapterGroup);
      }
      chapterGroup.chunks.push(chunk);
    }

    const sources = [...bySource.entries()].map(([source, chapters]) => {
      const chapterGroups = [...chapters.values()];
      chapterGroups.sort((a, b) => {
        if (a.chapterNumber != null && b.chapterNumber != null) return a.chapterNumber - b.chapterNumber;
        const at = a.title || a.sourceId || a.key;
        const bt = b.title || b.sourceId || b.key;
        return at.localeCompare(bt);
      });
      for (const g of chapterGroups) {
        g.chunks.sort((a, b) => a.chunkIndex - b.chunkIndex || a.id.localeCompare(b.id));
      }
      return { source, chapterGroups };
    });
    sources.sort((a, b) => a.source.localeCompare(b.source));
    return sources;
  }, [vectorResult]);

  const runVectorQuery = useCallback(async () => {
    if (!projectId) {
      setVectorError({ code: "NO_PROJECT", message: UI_COPY.writing.contextPreviewMissingProjectId });
      return;
    }
    if (selectedVectorSources.length === 0) {
      toast.toastError("至少选择一个 source");
      return;
    }
    setVectorLoading(true);
    setVectorError(null);
    try {
      const res = await apiJson<{
        result: unknown;
        raw_query_text?: unknown;
        normalized_query_text?: unknown;
        preprocess_obs?: unknown;
      }>(`/api/projects/${projectId}/vector/query`, {
        method: "POST",
        body: JSON.stringify({ query_text: vectorQueryText, sources: selectedVectorSources }),
      });
      const normalized = normalizeVectorResult(res.data?.result);
      if (!normalized)
        throw new ApiError({ code: "BAD_RESPONSE", message: "响应格式错误", requestId: res.request_id, status: 200 });
      setVectorResult(normalized);
      setVectorRequestId(res.request_id ?? null);
      setVectorRawQueryText(typeof res.data?.raw_query_text === "string" ? res.data.raw_query_text : vectorQueryText);
      setVectorNormalizedQueryText(
        typeof res.data?.normalized_query_text === "string" ? res.data.normalized_query_text : null,
      );
      setVectorPreprocessObs(res.data?.preprocess_obs ?? null);
    } catch (e) {
      setVectorRawQueryText(null);
      setVectorNormalizedQueryText(null);
      setVectorPreprocessObs(null);
      if (e instanceof ApiError) {
        setVectorError({ code: e.code, message: e.message, requestId: e.requestId });
      } else {
        setVectorError({ code: "UNKNOWN", message: "查询失败" });
      }
    } finally {
      setVectorLoading(false);
    }
  }, [projectId, selectedVectorSources, toast, vectorQueryText]);

  useEffect(() => {
    if (!open) return;
    setVectorError(null);
    setVectorRequestId(null);
    setVectorResult(null);
    setVectorLoading(false);
    setVectorRawQueryText(null);
    setVectorNormalizedQueryText(null);
    setVectorPreprocessObs(null);
  }, [open, projectId]);

  return {
    groupedVectorFinalChunks,
    runVectorQuery,
    selectedVectorSources,
    setVectorQueryText,
    setVectorSources,
    vectorError,
    vectorLoading,
    vectorNormalizedQueryText,
    vectorPreprocessObs,
    vectorQueryText,
    vectorRawQueryText,
    vectorRequestId,
    vectorResult,
    vectorSources,
  };
}
