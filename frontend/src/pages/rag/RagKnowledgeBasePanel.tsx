import { UI_COPY } from "../../lib/uiCopy";
import type { KnowledgeBase, VectorRagResult } from "./types";

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

      <div className="mt-3 grid gap-2">
        {kbs.length ? (
          kbs.map((kb) => {
            const draft = kbDraftById[kb.kb_id] ?? { name: kb.name, enabled: kb.enabled, weight: kb.weight };
            const dirty = Boolean(kbDirtyById[kb.kb_id]);
            const perKb = queryResult?.kbs?.per_kb?.[kb.kb_id];
            const counts = perKb?.counts;
            const isDragging = kbDragId === kb.kb_id;

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
                      <span className="font-medium">{kb.kb_id}</span>
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
                        !projectId || kbDeleteLoadingId === kb.kb_id || Boolean(draft.enabled) || kb.kb_id === "default"
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
