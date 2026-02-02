import { useMemo, useState, type ReactNode } from "react";

import { UI_COPY } from "../../lib/uiCopy";
import { containsPinyinMatch, looksLikePinyinToken, tokenizeSearch } from "../../lib/pinyin";
import type { KnowledgeBase, VectorRagResult } from "./types";

function highlightText(text: string, tokens: string[]): ReactNode {
  const raw = String(text ?? "");
  if (!raw) return raw;
  if (!tokens.length) return raw;

  const lower = raw.toLowerCase();
  const active = tokens.map((t) => String(t || "").toLowerCase()).filter((t) => t.length > 0 && lower.includes(t));
  if (!active.length) return raw;

  const uniq = [...new Set(active)].sort((a, b) => b.length - a.length);
  const out: ReactNode[] = [];
  let cursor = 0;

  while (cursor < raw.length) {
    let bestIdx = -1;
    let bestToken = "";
    for (const t of uniq) {
      const idx = lower.indexOf(t, cursor);
      if (idx < 0) continue;
      if (bestIdx < 0 || idx < bestIdx || (idx === bestIdx && t.length > bestToken.length)) {
        bestIdx = idx;
        bestToken = t;
      }
    }
    if (bestIdx < 0) {
      out.push(raw.slice(cursor));
      break;
    }
    if (bestIdx > cursor) out.push(raw.slice(cursor, bestIdx));
    const seg = raw.slice(bestIdx, bestIdx + bestToken.length);
    out.push(
      <mark key={`${bestIdx}:${bestToken}:${cursor}`} className="rounded bg-warning/20 px-0.5 text-ink">
        {seg}
      </mark>,
    );
    cursor = bestIdx + bestToken.length;
  }

  return <>{out}</>;
}

export function RagKnowledgeBasePanel(props: {
  projectId: string | undefined;
  kbLoading: boolean;
  kbOrderDirty: boolean;
  loadKbs: () => Promise<void>;
  saveKbOrder: () => Promise<void>;
  selectedKbIds: string[];
  queryResult: VectorRagResult | null;
  kbs: KnowledgeBase[];
  kbDraftById: Record<string, Pick<KnowledgeBase, "name" | "enabled" | "weight">>;
  kbDirtyById: Record<string, boolean>;
  kbDragId: string | null;
  setKbDragId: (id: string | null) => void;
  moveKb: (fromKbId: string, toKbId: string) => void;
  updateKbDraft: (kbId: string, patch: Partial<Pick<KnowledgeBase, "name" | "enabled" | "weight">>) => void;
  kbSaveLoadingId: string | null;
  kbDeleteLoadingId: string | null;
  saveKb: (kbId: string) => Promise<void>;
  deleteKb: (kbId: string) => Promise<void>;
  kbCreateName: string;
  setKbCreateName: (name: string) => void;
  kbCreateLoading: boolean;
  createKb: () => Promise<void>;
  toggleKbSelected: (kbId: string) => void;
}) {
  const {
    createKb,
    deleteKb,
    kbCreateLoading,
    kbCreateName,
    kbDeleteLoadingId,
    kbDirtyById,
    kbDragId,
    kbDraftById,
    kbLoading,
    kbOrderDirty,
    kbSaveLoadingId,
    kbs,
    loadKbs,
    moveKb,
    projectId,
    queryResult,
    saveKb,
    saveKbOrder,
    selectedKbIds,
    setKbCreateName,
    setKbDragId,
    toggleKbSelected,
    updateKbDraft,
  } = props;

  const [kbSearchText, setKbSearchText] = useState("");
  const kbTokens = useMemo(() => tokenizeSearch(kbSearchText), [kbSearchText]);

  const kbSearchMeta = useMemo(() => {
    const tokens = kbTokens;
    const metaById = new Map<string, { pinyinHit: boolean }>();
    if (!tokens.length) return { list: kbs, metaById, tokens };

    const list = kbs.filter((kb) => {
      const draft = kbDraftById[kb.kb_id] ?? { name: kb.name, enabled: kb.enabled, weight: kb.weight };
      const haystackId = String(kb.kb_id ?? "").toLowerCase();
      const haystackName = String(draft.name ?? "").toLowerCase();
      const combined = `${kb.kb_id} ${draft.name ?? ""}`;
      let pinyinHit = false;

      const ok = tokens.every((t) => {
        if (haystackId.includes(t)) return true;
        if (haystackName.includes(t)) return true;
        if (!looksLikePinyinToken(t)) return false;
        const m = containsPinyinMatch(combined, t);
        if (!m.matched) return false;
        pinyinHit = true;
        return true;
      });
      if (ok) metaById.set(kb.kb_id, { pinyinHit });
      return ok;
    });

    return { list, metaById, tokens };
  }, [kbDraftById, kbTokens, kbs]);

  const filteredKbs = kbSearchMeta.list;

  return (
    <div
      className="mt-6 rounded-atelier border border-border bg-surface p-4"
      role="region"
      aria-label="知识库 (rag_kb_section)"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm font-medium text-ink">{UI_COPY.rag.kbTitle}</div>
        <div className="flex gap-2">
          <button
            className="btn btn-secondary"
            disabled={!projectId || kbLoading}
            onClick={() => void loadKbs()}
            type="button"
          >
            {kbLoading ? "加载中…" : "刷新 KB"}
          </button>
          <button
            className="btn btn-primary"
            disabled={!projectId || kbLoading || !kbOrderDirty}
            onClick={() => void saveKbOrder()}
            type="button"
          >
            保存排序
          </button>
        </div>
      </div>

      <div className="mt-2 text-xs text-subtext">
        当前选择（selected_kb_ids）:{" "}
        {selectedKbIds.length ? selectedKbIds.join(", ") : "（空：查询默认使用“已启用”的 KB）"}
        {queryResult?.kbs?.selected?.length ? (
          <span className="ml-2">| 查询使用（query_selected）: {queryResult.kbs.selected.join(", ")}</span>
        ) : null}
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        <label className="grid gap-1">
          <span className="text-xs text-subtext">搜索 KB（支持拼音/首字母）</span>
          <input
            className="input"
            value={kbSearchText}
            onChange={(e) => setKbSearchText(e.target.value)}
            aria-label="rag_kb_search"
            placeholder="例如：beijing / bj / 世界书"
          />
          <div className="text-[11px] text-subtext">匹配：kb_id / 名称；拼音匹配失败时自动降级为普通包含匹配。</div>
        </label>
        <div className="flex items-end justify-end text-xs text-subtext">
          显示 {filteredKbs.length}/{kbs.length} 条
        </div>
      </div>

      <div className="mt-3 grid gap-2">
        {kbs.length ? (
          filteredKbs.length ? (
            filteredKbs.map((kb) => {
              const draft = kbDraftById[kb.kb_id] ?? { name: kb.name, enabled: kb.enabled, weight: kb.weight };
              const dirty = Boolean(kbDirtyById[kb.kb_id]);
              const perKb = queryResult?.kbs?.per_kb?.[kb.kb_id];
              const counts = perKb?.counts;
              const isDragging = kbDragId === kb.kb_id;
              const meta = kbSearchMeta.metaById.get(kb.kb_id) ?? { pinyinHit: false };

              return (
                <div
                  key={kb.kb_id}
                  className={
                    isDragging
                      ? "rounded-atelier border border-border bg-canvas p-3 opacity-80"
                      : "rounded-atelier border border-border bg-canvas p-3"
                  }
                  draggable
                  onDragStart={() => setKbDragId(kb.kb_id)}
                  onDragEnd={() => setKbDragId(null)}
                  onDragOver={(e) => {
                    e.preventDefault();
                    e.dataTransfer.dropEffect = "move";
                  }}
                  onDrop={() => {
                    if (!kbDragId) return;
                    moveKb(kbDragId, kb.kb_id);
                    setKbDragId(null);
                  }}
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-3">
                      <label className="flex items-center gap-2 text-sm text-ink">
                        <input
                          className="checkbox"
                          type="checkbox"
                          checked={selectedKbIds.includes(kb.kb_id)}
                          onChange={() => toggleKbSelected(kb.kb_id)}
                          aria-label={`选择 KB ${kb.kb_id}`}
                        />
                        <span className="font-medium">{highlightText(kb.kb_id, kbSearchMeta.tokens)}</span>
                        {meta.pinyinHit ? (
                          <span className="rounded border border-border bg-surface px-1 py-0.5 text-[10px] text-subtext">
                            拼音
                          </span>
                        ) : null}
                      </label>
                      <label className="flex items-center gap-2 text-sm text-ink">
                        <input
                          className="checkbox"
                          type="checkbox"
                          checked={Boolean(draft.enabled)}
                          onChange={(e) => updateKbDraft(kb.kb_id, { enabled: e.target.checked })}
                          aria-label={`启用 KB ${kb.kb_id}`}
                        />
                        启用
                      </label>
                      <label className="flex items-center gap-2 text-sm text-ink">
                        <span className="text-xs text-subtext">权重（weight）</span>
                        <input
                          className="input w-24"
                          type="number"
                          step="0.1"
                          value={String(draft.weight ?? 1)}
                          onChange={(e) => {
                            const next = Number(e.target.value);
                            if (!Number.isFinite(next)) return;
                            updateKbDraft(kb.kb_id, { weight: next });
                          }}
                          aria-label={`KB 权重 ${kb.kb_id}`}
                        />
                      </label>
                      <label className="flex items-center gap-2 text-sm text-ink">
                        <span className="text-xs text-subtext">{UI_COPY.rag.kbNameLabel}</span>
                        <input
                          className="input w-56"
                          value={draft.name}
                          onChange={(e) => updateKbDraft(kb.kb_id, { name: e.target.value })}
                          aria-label={`KB 名称 ${kb.kb_id}`}
                        />
                      </label>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        className="btn btn-primary"
                        disabled={!projectId || kbSaveLoadingId === kb.kb_id || !dirty}
                        onClick={() => void saveKb(kb.kb_id)}
                        aria-label={`保存 KB ${kb.kb_id}`}
                        type="button"
                      >
                        {kbSaveLoadingId === kb.kb_id ? "保存中…" : dirty ? "保存" : "已保存"}
                      </button>
                      <button
                        className="btn btn-danger"
                        disabled={
                          !projectId ||
                          kbDeleteLoadingId === kb.kb_id ||
                          Boolean(draft.enabled) ||
                          kb.kb_id === "default"
                        }
                        onClick={() => void deleteKb(kb.kb_id)}
                        aria-label={`删除 KB ${kb.kb_id}`}
                        type="button"
                      >
                        {kbDeleteLoadingId === kb.kb_id ? "删除中…" : "删除"}
                      </button>
                    </div>
                  </div>

                  <div className="mt-2 flex flex-wrap gap-3 text-xs text-subtext">
                    <div>
                      {UI_COPY.rag.kbOrderLabel}: {kb.order}
                    </div>
                    <div>
                      {UI_COPY.rag.kbEnabledLabel}: {String(Boolean(draft.enabled))}
                    </div>
                    <div>
                      {UI_COPY.rag.kbWeightLabel}: {String(draft.weight)}
                    </div>
                    {counts ? (
                      <div>
                        query_counts: {counts.candidates_total}/{counts.candidates_returned} | final:
                        {counts.final_selected} | dropped:{counts.dropped_total}
                      </div>
                    ) : (
                      <div>query_counts: -</div>
                    )}
                  </div>
                </div>
              );
            })
          ) : (
            <div className="text-xs text-subtext">无匹配 KB。</div>
          )
        ) : (
          <div className="text-xs text-subtext">暂无 KB（将自动创建 default）。</div>
        )}
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-4">
        <label className="grid gap-1 sm:col-span-3">
          <span className="text-xs text-subtext">{UI_COPY.rag.kbNewNameLabel}</span>
          <input
            className="input"
            value={kbCreateName}
            onChange={(e) => setKbCreateName(e.target.value)}
            aria-label="kb_create_name"
            placeholder={UI_COPY.rag.kbNewNamePlaceholder}
          />
        </label>
        <div className="flex items-end">
          <button
            className="btn btn-primary w-full"
            disabled={!projectId || kbCreateLoading}
            onClick={() => void createKb()}
            aria-label="创建 KB (rag_kb_create)"
            type="button"
          >
            {kbCreateLoading ? "创建中…" : "创建 KB"}
          </button>
        </div>
      </div>
    </div>
  );
}
