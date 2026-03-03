import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useToast } from "../../components/ui/toast";
import { ApiError, apiJson } from "../../services/apiClient";

type EntityRow = {
  id: string;
  entity_type: string;
  name: string;
  deleted_at?: string | null;
};

type RelationRow = {
  id: string;
  relation_type: string;
  from_entity_id: string;
  to_entity_id: string;
  description_md?: string | null;
  deleted_at?: string | null;
};

type EvidenceRow = {
  id: string;
  source_type: string;
  source_id?: string | null;
  quote_md?: string | null;
  deleted_at?: string | null;
  created_at?: string | null;
};

type StructuredMemoryResponse = {
  entities?: EntityRow[];
  relations?: RelationRow[];
  evidence?: EvidenceRow[];
};

type MemoryUpdateProposeResponse = {
  idempotent: boolean;
  change_set?: { id: string; request_id?: string | null };
  items?: unknown[];
};

type MemoryUpdateApplyResponse = {
  idempotent: boolean;
  change_set?: { id: string };
  warnings?: Array<{ code?: string; message?: string; item_id?: string }>;
};

const RECOMMENDED_RELATION_TYPES = [
  "related_to",
  "family",
  "romance",
  "friend",
  "ally",
  "enemy",
  "mentor",
  "student",
  "leader_of",
  "member_of",
  "owes",
  "betrayed",
  "protects",
] as const;

function safeRandomUUID(): string {
  try {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  } catch {
    // ignore
  }

  const template = "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx";
  return template.replace(/[xy]/g, (c) => {
    const r = Math.floor(Math.random() * 16);
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}
export function CharacterRelationsView(props: {
  projectId: string;
  chapterId?: string;
  focusRelationId?: string | null;
  includeDeleted: boolean;
  onRequestId: (value: string | null) => void;
}) {
  const { projectId, chapterId, focusRelationId, includeDeleted, onRequestId } = props;
  const toast = useToast();

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rollingBack, setRollingBack] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [lastChangeSetId, setLastChangeSetId] = useState<string>("");

  const [characters, setCharacters] = useState<EntityRow[]>([]);
  const [relations, setRelations] = useState<RelationRow[]>([]);

  const [evidenceOpen, setEvidenceOpen] = useState<Record<string, boolean>>({});
  const [evidenceLoading, setEvidenceLoading] = useState<Record<string, boolean>>({});
  const [evidenceByRelationId, setEvidenceByRelationId] = useState<Record<string, EvidenceRow[]>>({});

  const characterIdToName = useMemo(() => {
    const map = new Map<string, string>();
    for (const c of characters) map.set(String(c.id), String(c.name || ""));
    return map;
  }, [characters]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const entityParams = new URLSearchParams();
      entityParams.set("table", "entities");
      entityParams.set("q", "character");
      entityParams.set("limit", "200");
      if (includeDeleted) entityParams.set("include_deleted", "true");

      const relationParams = new URLSearchParams();
      relationParams.set("table", "relations");
      relationParams.set("limit", "200");
      if (includeDeleted) relationParams.set("include_deleted", "true");

      const [entitiesRes, relationsRes] = await Promise.all([
        apiJson<StructuredMemoryResponse>(`/api/projects/${projectId}/memory/structured?${entityParams.toString()}`),
        apiJson<StructuredMemoryResponse>(`/api/projects/${projectId}/memory/structured?${relationParams.toString()}`),
      ]);
      onRequestId(relationsRes.request_id ?? entitiesRes.request_id ?? null);

      const rawEntities = (entitiesRes.data?.entities ?? []) as EntityRow[];
      const activeChars = rawEntities
        .filter((e) => (e.entity_type || "").trim() === "character" && (includeDeleted || !e.deleted_at))
        .sort((a, b) => String(a.name || "").localeCompare(String(b.name || ""), "zh-Hans-CN"));
      setCharacters(activeChars);

      const charIdSet = new Set(activeChars.map((e) => String(e.id)));
      const charIdToName = new Map(activeChars.map((e) => [String(e.id), String(e.name || "")] as const));

      const rawRelations = (relationsRes.data?.relations ?? []) as RelationRow[];
      const filteredRelations = rawRelations
        .filter((r) => {
          if (!includeDeleted && r.deleted_at) return false;
          return charIdSet.has(String(r.from_entity_id)) && charIdSet.has(String(r.to_entity_id));
        })
        .sort((a, b) => {
          const aKey = `${charIdToName.get(String(a.from_entity_id)) || ""}|${a.relation_type || ""}|${charIdToName.get(String(a.to_entity_id)) || ""}|${a.id}`;
          const bKey = `${charIdToName.get(String(b.from_entity_id)) || ""}|${b.relation_type || ""}|${charIdToName.get(String(b.to_entity_id)) || ""}|${b.id}`;
          return aKey.localeCompare(bKey, "zh-Hans-CN");
        });
      setRelations(filteredRelations);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      onRequestId(err.requestId ?? null);
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [includeDeleted, onRequestId, projectId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const [createFromId, setCreateFromId] = useState("");
  const [createToId, setCreateToId] = useState("");
  const [createType, setCreateType] = useState<string>("related_to");
  const [createDesc, setCreateDesc] = useState("");

  useEffect(() => {
    if (!characters.length) return;
    setCreateFromId((prev) => prev || String(characters[0].id));
    setCreateToId((prev) => prev || String(characters[Math.min(1, characters.length - 1)].id));
  }, [characters]);

  const runChangeSet = useCallback(
    async (opts: { title: string; ops: unknown[] }) => {
      if (!chapterId) {
        toast.toastWarning("缺少 chapterId：请从写作页带上 ?chapterId=... 打开，以便写入变更集。");
        return;
      }
      setSaving(true);
      try {
        const proposeRes = await apiJson<MemoryUpdateProposeResponse>(`/api/chapters/${chapterId}/memory/propose`, {
          method: "POST",
          body: JSON.stringify({
            schema_version: "memory_update_v1",
            idempotency_key: `ui-graph-${safeRandomUUID().slice(0, 12)}`,
            title: opts.title,
            ops: opts.ops,
          }),
        });
        onRequestId(proposeRes.request_id ?? null);
        const changeSetId = proposeRes.data?.change_set?.id;
        if (!changeSetId) throw new Error("change_set_id missing");

        const applyRes = await apiJson<MemoryUpdateApplyResponse>(`/api/memory_change_sets/${changeSetId}/apply`, {
          method: "POST",
        });
        onRequestId(applyRes.request_id ?? null);

        const warnings = applyRes.data?.warnings ?? [];
        if (warnings.length) toast.toastWarning(`已应用，但有 ${warnings.length} 条 warning`, applyRes.request_id);
        else toast.toastSuccess("已应用变更集", applyRes.request_id);

        setLastChangeSetId(String(changeSetId));
        setEvidenceByRelationId({});
        setEvidenceOpen({});
        await refresh();
      } catch (e) {
        const err =
          e instanceof ApiError
            ? e
            : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
        onRequestId(err.requestId ?? null);
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setSaving(false);
      }
    },
    [chapterId, onRequestId, refresh, toast],
  );

  const rollbackLastChangeSet = useCallback(async () => {
    const id = lastChangeSetId.trim();
    if (!id) return;
    setRollingBack(true);
    try {
      const res = await apiJson<{ idempotent?: boolean; change_set?: { id: string } }>(
        `/api/memory_change_sets/${encodeURIComponent(id)}/rollback`,
        { method: "POST" },
      );
      onRequestId(res.request_id ?? null);
      toast.toastSuccess("已回滚最近变更集", res.request_id);
      setEvidenceByRelationId({});
      setEvidenceOpen({});
      setEditingId(null);
      await refresh();
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      onRequestId(err.requestId ?? null);
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setRollingBack(false);
    }
  }, [lastChangeSetId, onRequestId, refresh, toast]);

  const createRelation = useCallback(async () => {
    const fromId = createFromId.trim();
    const toId = createToId.trim();
    if (!fromId || !toId) {
      toast.toastWarning("请选择 from/to 人物");
      return;
    }
    const relType = (createType || "related_to").trim() || "related_to";
    const relId = safeRandomUUID();
    await runChangeSet({
      title: "UI: 维护人物关系（relations upsert）",
      ops: [
        {
          op: "upsert",
          target_table: "relations",
          target_id: relId,
          after: {
            from_entity_id: fromId,
            to_entity_id: toId,
            relation_type: relType,
            description_md: createDesc.trim() || null,
          },
        },
      ],
    });
    setCreateDesc("");
  }, [createDesc, createFromId, createToId, createType, runChangeSet, toast]);

  const [editingId, setEditingId] = useState<string | null>(null);
  const editing = useMemo(
    () => relations.find((r) => String(r.id) === String(editingId)) ?? null,
    [editingId, relations],
  );
  const [editFromId, setEditFromId] = useState("");
  const [editToId, setEditToId] = useState("");
  const [editType, setEditType] = useState("");
  const [editDesc, setEditDesc] = useState("");

  useEffect(() => {
    if (!editing) return;
    setEditFromId(String(editing.from_entity_id));
    setEditToId(String(editing.to_entity_id));
    setEditType(String(editing.relation_type || "related_to"));
    setEditDesc(String(editing.description_md || ""));
  }, [editing]);

  const saveEdit = useCallback(async () => {
    if (!editing) return;
    const relId = String(editing.id);
    const relType = (editType || "related_to").trim() || "related_to";
    await runChangeSet({
      title: "UI: 编辑人物关系（relations upsert）",
      ops: [
        {
          op: "upsert",
          target_table: "relations",
          target_id: relId,
          after: {
            from_entity_id: editFromId.trim(),
            to_entity_id: editToId.trim(),
            relation_type: relType,
            description_md: editDesc.trim() || null,
          },
        },
      ],
    });
    setEditingId(null);
  }, [editDesc, editFromId, editToId, editType, editing, runChangeSet]);

  const deleteRelation = useCallback(
    async (relId: string) => {
      if (!relId) return;
      await runChangeSet({
        title: "UI: 删除人物关系（relations delete）",
        ops: [{ op: "delete", target_table: "relations", target_id: String(relId) }],
      });
      if (String(editingId) === String(relId)) setEditingId(null);
    },
    [editingId, runChangeSet],
  );

  const toggleEvidence = useCallback(
    async (relId: string) => {
      const nextOpen = !evidenceOpen[relId];
      setEvidenceOpen((prev) => ({ ...prev, [relId]: nextOpen }));
      if (!nextOpen) return;
      if (evidenceByRelationId[relId]) return;

      setEvidenceLoading((prev) => ({ ...prev, [relId]: true }));
      try {
        const params = new URLSearchParams();
        params.set("table", "evidence");
        params.set("q", relId);
        params.set("limit", "80");
        if (includeDeleted) params.set("include_deleted", "true");
        const res = await apiJson<StructuredMemoryResponse>(
          `/api/projects/${projectId}/memory/structured?${params.toString()}`,
        );
        onRequestId(res.request_id ?? null);
        const evs = ((res.data?.evidence ?? []) as EvidenceRow[]).filter(
          (ev) => String(ev.source_id || "") === String(relId) && (includeDeleted || !ev.deleted_at),
        );
        setEvidenceByRelationId((prev) => ({ ...prev, [relId]: evs }));
      } catch (e) {
        const err =
          e instanceof ApiError
            ? e
            : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
        onRequestId(err.requestId ?? null);
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setEvidenceLoading((prev) => ({ ...prev, [relId]: false }));
      }
    },
    [evidenceByRelationId, evidenceOpen, includeDeleted, onRequestId, projectId, toast],
  );

  useEffect(() => {
    const rid = String(focusRelationId || "").trim();
    if (!rid) return;
    if (!relations.some((r) => String(r.id) === rid)) return;
    setEditingId(rid);
    if (!evidenceOpen[rid]) void toggleEvidence(rid);
  }, [evidenceOpen, focusRelationId, relations, toggleEvidence]);

  return (
    <div className="grid gap-3">
      <div className="rounded-atelier border border-border bg-canvas p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm text-ink">人物关系（entity_type=character）</div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => void refresh()}
              disabled={loading}
              type="button"
            >
              {loading ? "刷新..." : "刷新"}
            </button>
            <Link
              className="btn btn-secondary btn-sm"
              to={`/projects/${projectId}/graph`}
              aria-label="structured_character_relations_open_graph"
            >
              去图谱 Query
            </Link>
          </div>
        </div>
        <div className="mt-1 text-xs text-subtext">
          提示：该视图会过滤出人物实体，并提供关系 CRUD；写入将走 Memory Update 变更集（需要 ?chapterId）。
        </div>
        {lastChangeSetId ? (
          <div className="mt-2 rounded-atelier border border-border bg-surface p-2 text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-subtext">
                最近变更集：<span className="font-mono text-ink">{lastChangeSetId}</span>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Link className="btn btn-secondary btn-sm" to={`/projects/${projectId}/tasks`}>
                  打开 Task Center
                </Link>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => void rollbackLastChangeSet()}
                  aria-label="structured_character_relations_rollback_last"
                  disabled={saving || rollingBack}
                  type="button"
                >
                  {rollingBack ? "回滚中..." : "回滚最近变更集"}
                </button>
              </div>
            </div>
          </div>
        ) : null}
        {!chapterId ? (
          <div className="mt-2 rounded-atelier border border-border bg-surface p-2 text-xs text-amber-700 dark:text-amber-300">
            缺少 chapterId：创建/编辑/删除会被禁用。建议从写作页进入，或手动在 URL 加上 ?chapterId=...。
          </div>
        ) : null}
        {error ? (
          <div className="mt-2 rounded-atelier border border-border bg-surface p-2 text-xs text-subtext">
            {error.message} ({error.code}) {error.requestId ? `| request_id: ${error.requestId}` : ""}
          </div>
        ) : null}
      </div>

      <div className="rounded-atelier border border-border bg-canvas p-3">
        <div className="text-sm text-ink">新增关系</div>
        <div className="mt-2 grid gap-3 lg:grid-cols-4">
          <label className="grid gap-1">
            <span className="text-xs text-subtext">From</span>
            <select
              className="select"
              id="structured_character_relations_create_from"
              name="structured_character_relations_create_from"
              value={createFromId}
              onChange={(e) => setCreateFromId(e.target.value)}
              aria-label="structured_character_relations_create_from"
              disabled={!chapterId || saving}
            >
              <option value="">（请选择）</option>
              {characters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>

          <label className="grid gap-1">
            <span className="text-xs text-subtext">关系类型（relation_type）</span>
            <input
              className="input"
              value={createType}
              onChange={(e) => setCreateType(e.target.value)}
              aria-label="structured_character_relations_create_type"
              list="structured_relation_types"
              disabled={!chapterId || saving}
            />
          </label>

          <label className="grid gap-1">
            <span className="text-xs text-subtext">To</span>
            <select
              className="select"
              id="structured_character_relations_create_to"
              name="structured_character_relations_create_to"
              value={createToId}
              onChange={(e) => setCreateToId(e.target.value)}
              aria-label="structured_character_relations_create_to"
              disabled={!chapterId || saving}
            >
              <option value="">（请选择）</option>
              {characters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>

          <div className="flex items-end">
            <button
              className="btn btn-primary w-full"
              onClick={() => void createRelation()}
              aria-label="structured_character_relations_create_submit"
              disabled={!chapterId || saving}
              type="button"
            >
              {saving ? "提交中..." : "新增"}
            </button>
          </div>
        </div>
        <datalist id="structured_relation_types">
          {RECOMMENDED_RELATION_TYPES.map((t) => (
            <option key={t} value={t} />
          ))}
        </datalist>
        <label className="mt-3 grid gap-1">
          <span className="text-xs text-subtext">描述（description_md，可选）</span>
          <textarea
            className="textarea"
            rows={2}
            value={createDesc}
            onChange={(e) => setCreateDesc(e.target.value)}
            aria-label="structured_character_relations_create_desc"
            disabled={!chapterId || saving}
          />
        </label>
      </div>

      <div className="rounded-atelier border border-border bg-canvas p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm text-ink">
            关系列表 <span className="text-xs text-subtext">({relations.length})</span>
          </div>
          <div className="text-xs text-subtext">
            人物：{characters.length} | include_deleted: {includeDeleted ? "true" : "false"}
          </div>
        </div>
        {!relations.length && !loading ? <div className="mt-2 text-sm text-subtext">暂无人物关系</div> : null}
        <div className="mt-2 grid gap-2">
          {relations.map((r) => {
            const relId = String(r.id);
            const fromName = characterIdToName.get(String(r.from_entity_id)) || String(r.from_entity_id);
            const toName = characterIdToName.get(String(r.to_entity_id)) || String(r.to_entity_id);
            const relType = String(r.relation_type || "related_to");
            const isEditing = relId === String(editingId || "");
            const open = !!evidenceOpen[relId];
            const evLoading = !!evidenceLoading[relId];
            const ev = evidenceByRelationId[relId] ?? null;

            return (
              <div
                key={relId}
                className="rounded-atelier border border-border bg-surface p-3"
                aria-label={`structured_character_relation_${relId}`}
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="text-sm text-ink">
                      {fromName} --({relType})→ {toName}
                    </div>
                    <div className="mt-1 text-[11px] text-subtext">{relId}</div>
                    {r.deleted_at ? (
                      <div className="mt-1 text-[11px] text-danger">deleted_at: {r.deleted_at}</div>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => setEditingId(isEditing ? null : relId)}
                      aria-label={`structured_character_relation_edit_${relId}`}
                      disabled={!chapterId || saving}
                      type="button"
                    >
                      {isEditing ? "取消编辑" : "编辑"}
                    </button>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => void deleteRelation(relId)}
                      aria-label={`structured_character_relation_delete_${relId}`}
                      disabled={!chapterId || saving}
                      type="button"
                    >
                      删除
                    </button>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => void toggleEvidence(relId)}
                      aria-label={`structured_character_relation_toggle_evidence_${relId}`}
                      type="button"
                    >
                      {open ? "收起证据" : "展开证据"}
                    </button>
                  </div>
                </div>

                {r.description_md ? (
                  <div className="mt-2 whitespace-pre-wrap text-sm text-subtext">{r.description_md}</div>
                ) : null}

                {isEditing ? (
                  <div className="mt-3 grid gap-3 rounded-atelier border border-border bg-canvas p-3">
                    <div className="text-xs text-subtext">编辑关系（upsert）</div>
                    <div className="grid gap-3 lg:grid-cols-4">
                      <label className="grid gap-1">
                        <span className="text-xs text-subtext">From</span>
                        <select
                          className="select"
                          id="structured_character_relations_edit_from"
                          name="structured_character_relations_edit_from"
                          value={editFromId}
                          onChange={(e) => setEditFromId(e.target.value)}
                          aria-label="structured_character_relations_edit_from"
                          disabled={!chapterId || saving}
                        >
                          <option value="">（请选择）</option>
                          {characters.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="grid gap-1">
                        <span className="text-xs text-subtext">关系类型</span>
                        <input
                          className="input"
                          value={editType}
                          onChange={(e) => setEditType(e.target.value)}
                          list="structured_relation_types"
                          aria-label="structured_character_relations_edit_type"
                          disabled={!chapterId || saving}
                        />
                      </label>
                      <label className="grid gap-1">
                        <span className="text-xs text-subtext">To</span>
                        <select
                          className="select"
                          id="structured_character_relations_edit_to"
                          name="structured_character_relations_edit_to"
                          value={editToId}
                          onChange={(e) => setEditToId(e.target.value)}
                          aria-label="structured_character_relations_edit_to"
                          disabled={!chapterId || saving}
                        >
                          <option value="">（请选择）</option>
                          {characters.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <div className="flex items-end">
                        <button
                          className="btn btn-primary w-full"
                          onClick={() => void saveEdit()}
                          aria-label="structured_character_relations_edit_submit"
                          disabled={!chapterId || saving}
                          type="button"
                        >
                          {saving ? "保存中..." : "保存"}
                        </button>
                      </div>
                    </div>
                    <label className="grid gap-1">
                      <span className="text-xs text-subtext">描述（可选）</span>
                      <textarea
                        className="textarea"
                        rows={2}
                        value={editDesc}
                        onChange={(e) => setEditDesc(e.target.value)}
                        aria-label="structured_character_relations_edit_desc"
                        disabled={!chapterId || saving}
                      />
                    </label>
                  </div>
                ) : null}

                {open ? (
                  <div className="mt-3 rounded-atelier border border-border bg-canvas p-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-xs text-subtext">证据（source_id = relation_id）</div>
                      <div className="text-[11px] text-subtext">
                        {evLoading ? "加载中..." : ev ? `共 ${ev.length} 条` : "未加载"}
                      </div>
                    </div>
                    {evLoading ? <div className="mt-2 text-xs text-subtext">加载中...</div> : null}
                    {!evLoading && ev && ev.length === 0 ? (
                      <div className="mt-2 text-xs text-subtext">暂无证据</div>
                    ) : null}
                    {!evLoading && ev && ev.length > 0 ? (
                      <div className="mt-2 grid gap-2">
                        {ev.map((item) => (
                          <div
                            key={String(item.id)}
                            className="rounded-atelier border border-border bg-surface p-2 text-xs"
                            aria-label={`structured_character_relation_evidence_${relId}_${String(item.id)}`}
                          >
                            <div className="text-[11px] text-subtext">
                              {item.source_type}:{item.source_id ?? "-"} | {item.created_at ?? "-"}
                            </div>
                            <div className="mt-1 whitespace-pre-wrap text-subtext">{item.quote_md || "（空）"}</div>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
