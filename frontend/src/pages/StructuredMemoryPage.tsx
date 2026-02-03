import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { DebugDetails, DebugPageShell } from "../components/atelier/DebugPageShell";
import { Drawer } from "../components/ui/Drawer";
import { RequestIdBadge } from "../components/ui/RequestIdBadge";
import { useToast } from "../components/ui/toast";
import { MemoryUpdateDrawer } from "../components/writing/MemoryUpdateDrawer";
import { useProjectData } from "../hooks/useProjectData";
import { UI_COPY } from "../lib/uiCopy";
import { ApiError, apiJson } from "../services/apiClient";

type TableName = "entities" | "relations" | "events" | "foreshadows" | "evidence";
type ViewMode = "table" | "character_relations";

type Counts = Record<TableName, number>;

type EntityRow = {
  id: string;
  entity_type: string;
  name: string;
  summary_md?: string | null;
  deleted_at?: string | null;
  updated_at?: string | null;
};

type RelationRow = {
  id: string;
  relation_type: string;
  from_entity_id: string;
  to_entity_id: string;
  description_md?: string | null;
  deleted_at?: string | null;
  updated_at?: string | null;
};

type EventRow = {
  id: string;
  chapter_id?: string | null;
  event_type: string;
  title?: string | null;
  content_md?: string | null;
  deleted_at?: string | null;
  updated_at?: string | null;
};

type ForeshadowRow = {
  id: string;
  chapter_id?: string | null;
  resolved_at_chapter_id?: string | null;
  title?: string | null;
  content_md?: string | null;
  resolved: number;
  deleted_at?: string | null;
  updated_at?: string | null;
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
  counts: Counts;
  cursor: Partial<Record<TableName, string | null>>;
  entities?: EntityRow[];
  relations?: RelationRow[];
  events?: EventRow[];
  foreshadows?: ForeshadowRow[];
  evidence?: EvidenceRow[];
};

type PageData = {
  table: TableName;
  q: string;
  include_deleted: boolean;
  counts: Counts;
  cursor: string | null;
  items: Array<Record<string, unknown>>;
};

const STRUCTURED_TABLE_LABELS: Record<TableName, string> = {
  entities: UI_COPY.structuredMemory.tabs.entities,
  relations: UI_COPY.structuredMemory.tabs.relations,
  events: UI_COPY.structuredMemory.tabs.events,
  foreshadows: UI_COPY.structuredMemory.tabs.foreshadows,
  evidence: UI_COPY.structuredMemory.tabs.evidence,
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

function tableLabel(t: TableName): string {
  return STRUCTURED_TABLE_LABELS[t] ?? t;
}

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

function safeSnippet(text: string | null | undefined, max = 80): string {
  const s = String(text || "")
    .replaceAll("\n", " ")
    .trim();
  if (!s) return "-";
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

function safeJsonStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function toCountMap(value: unknown): Counts {
  const base: Counts = { entities: 0, relations: 0, events: 0, foreshadows: 0, evidence: 0 };
  if (!value || typeof value !== "object") return base;
  const o = value as Record<string, unknown>;
  for (const key of Object.keys(base)) {
    const v = o[key];
    if (typeof v === "number" && Number.isFinite(v)) {
      base[key as TableName] = v;
    }
  }
  return base;
}

function toRowItems(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value.filter((x): x is Record<string, unknown> => !!x && typeof x === "object") as Array<
    Record<string, unknown>
  >;
}

function readStringField(row: Record<string, unknown>, key: string): string {
  const value = row[key];
  if (typeof value === "string") return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (value == null) return "";
  return String(value);
}

function readTextField(row: Record<string, unknown>, key: string): string | null | undefined {
  const value = row[key];
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return value;
  return String(value);
}

function readBoolField(row: Record<string, unknown>, key: string): boolean {
  const value = row[key];
  return value === true || value === 1 || value === "1" || value === "true";
}

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

function CharacterRelationsView(props: {
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

export function StructuredMemoryPage() {
  const { projectId } = useParams();
  const [searchParams] = useSearchParams();
  const toast = useToast();

  const chapterId = searchParams.get("chapterId") || undefined;
  const initialView: ViewMode = searchParams.get("view") === "character-relations" ? "character_relations" : "table";
  const [viewMode, setViewMode] = useState<ViewMode>(initialView);
  const focusRelationId = String(searchParams.get("relationId") || "").trim() || null;

  const [activeTable, setActiveTable] = useState<TableName>("entities");
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [searchText, setSearchText] = useState("");
  const [queryText, setQueryText] = useState("");
  const [requestId, setRequestId] = useState<string | null>(null);

  const [memoryUpdateOpen, setMemoryUpdateOpen] = useState(false);
  const [bulkOpsOpen, setBulkOpsOpen] = useState(false);

  const loader = useCallback(
    async (id: string): Promise<PageData> => {
      const params = new URLSearchParams();
      params.set("table", activeTable);
      if (includeDeleted) params.set("include_deleted", "true");
      if (queryText.trim()) params.set("q", queryText.trim());
      params.set("limit", "50");

      try {
        const res = await apiJson<StructuredMemoryResponse>(
          `/api/projects/${id}/memory/structured?${params.toString()}`,
        );
        setRequestId(res.request_id ?? null);
        const data = res.data as unknown as StructuredMemoryResponse;
        const counts = toCountMap(data.counts);
        const cursor = (data.cursor?.[activeTable] ?? null) as string | null;
        const items = toRowItems(data[activeTable]);

        return { table: activeTable, q: queryText.trim(), include_deleted: includeDeleted, counts, cursor, items };
      } catch (e) {
        if (e instanceof ApiError) setRequestId(e.requestId ?? null);
        throw e;
      }
    },
    [activeTable, includeDeleted, queryText],
  );

  const pageQuery = useProjectData(projectId, loader);
  const refresh = pageQuery.refresh;

  useEffect(() => {
    if (!projectId) return;
    void refresh();
  }, [activeTable, includeDeleted, projectId, queryText, refresh]);

  const counts = useMemo(
    () => pageQuery.data?.counts ?? { entities: 0, relations: 0, events: 0, foreshadows: 0, evidence: 0 },
    [pageQuery.data?.counts],
  );
  const cursor = pageQuery.data?.cursor ?? null;
  const items = useMemo(() => pageQuery.data?.items ?? [], [pageQuery.data?.items]);

  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);

  const loadMore = useCallback(async () => {
    if (!projectId) return;
    if (!cursor) return;
    const params = new URLSearchParams();
    params.set("table", activeTable);
    if (includeDeleted) params.set("include_deleted", "true");
    if (queryText.trim()) params.set("q", queryText.trim());
    params.set("before", cursor);
    params.set("limit", "50");

    try {
      const res = await apiJson<StructuredMemoryResponse>(
        `/api/projects/${projectId}/memory/structured?${params.toString()}`,
      );
      setRequestId(res.request_id ?? null);
      const data = res.data as unknown as StructuredMemoryResponse;
      const nextItems = toRowItems(data[activeTable]);
      const nextCursor = (data.cursor?.[activeTable] ?? null) as string | null;
      pageQuery.setData((prev) => {
        const prevCounts = prev?.counts ?? counts;
        return {
          table: activeTable,
          q: queryText.trim(),
          include_deleted: includeDeleted,
          counts: toCountMap(data.counts) ?? prevCounts,
          cursor: nextCursor,
          items: [...(prev?.items ?? []), ...nextItems],
        };
      });
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      setRequestId(err.requestId ?? null);
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    }
  }, [activeTable, counts, cursor, includeDeleted, pageQuery, projectId, queryText, toast]);

  const generatedDeleteOpsJson = useMemo(() => {
    if (selectedIds.length === 0) return "";
    const ops = selectedIds.map((id) => ({ op: "delete", target_table: activeTable, target_id: id }));
    return safeJsonStringify(ops);
  }, [activeTable, selectedIds]);

  const generatedResolvedOpsJson = useMemo(() => {
    if (activeTable !== "foreshadows" || selectedIds.length === 0) return "";
    const ops = selectedIds.map((id) => ({
      op: "upsert",
      target_table: "foreshadows",
      target_id: id,
      after: { resolved: 1 },
    }));
    return safeJsonStringify(ops);
  }, [activeTable, selectedIds]);

  const copyText = useCallback(
    async (text: string, label: string) => {
      if (!text.trim()) return;
      try {
        await navigator.clipboard.writeText(text);
        toast.toastSuccess(`已复制 ${label}`);
      } catch {
        toast.toastWarning(`复制失败，请手动复制下方 JSON（${label}）`);
      }
    },
    [toast],
  );

  const toggleSelected = useCallback((id: string, checked: boolean) => {
    setSelectedIds((prev) => {
      const set = new Set(prev);
      if (checked) set.add(id);
      else set.delete(id);
      const next = Array.from(set);
      if (next.length === 0) setBulkOpsOpen(false);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    const ids = items.map((row) => readStringField(row, "id")).filter(Boolean);
    setSelectedIds(ids);
  }, [items]);

  const clearSelected = useCallback(() => {
    setBulkOpsOpen(false);
    setSelectedIds([]);
  }, []);

  const applySearch = useCallback(() => {
    setBulkOpsOpen(false);
    setSelectedIds([]);
    setQueryText(searchText.trim());
  }, [searchText]);

  if (!projectId) return <div className="text-subtext">缺少 projectId</div>;

  return (
    <DebugPageShell
      title={UI_COPY.structuredMemory.title}
      description={UI_COPY.structuredMemory.subtitle}
      actions={
        <>
          <button className="btn btn-secondary" onClick={() => void pageQuery.refresh()} type="button">
            刷新
          </button>
          {selectedIds.length > 0 ? (
            <button className="btn btn-secondary" onClick={() => setBulkOpsOpen(true)} type="button">
              批量操作 ({selectedIds.length})
            </button>
          ) : null}
          <button
            className="btn btn-secondary"
            disabled={!chapterId}
            title={chapterId ? undefined : "建议从写作页带上 ?chapterId=... 打开以便 Apply"}
            onClick={() => setMemoryUpdateOpen(true)}
            type="button"
          >
            Memory Update
          </button>
        </>
      }
    >
      {projectId ? (
        <div className="callout-info text-sm">
          提示：本页是图谱底座数据（实体/关系/事件/伏笔/证据）。金钱/时间/等级/资源等数值状态请到{" "}
          <Link className="underline" to={`/projects/${projectId}/numeric-tables`}>
            {UI_COPY.nav.numericTables}
          </Link>
          。
        </div>
      ) : null}
      <div className="rounded-atelier border border-border bg-canvas p-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <button
              className={`btn ${viewMode === "table" ? "btn-primary" : "btn-secondary"}`}
              onClick={() => {
                setBulkOpsOpen(false);
                setSelectedIds([]);
                setViewMode("table");
              }}
              aria-label="structured_view_table"
              type="button"
            >
              数据表
            </button>
            <button
              className={`btn ${viewMode === "character_relations" ? "btn-primary" : "btn-secondary"}`}
              onClick={() => {
                setBulkOpsOpen(false);
                setSelectedIds([]);
                setViewMode("character_relations");
              }}
              aria-label="structured_view_character_relations"
              type="button"
            >
              人物关系
            </button>

            {viewMode === "table"
              ? (["entities", "relations", "events", "foreshadows", "evidence"] as const).map((t) => (
                  <button
                    key={t}
                    className={`btn ${activeTable === t ? "btn-primary" : "btn-secondary"}`}
                    onClick={() => {
                      setBulkOpsOpen(false);
                      setSelectedIds([]);
                      setActiveTable(t);
                    }}
                    aria-label={`${t}（${tableLabel(t)}） (structured_tab_${t})`}
                    type="button"
                  >
                    {tableLabel(t)} <span className="text-xs opacity-80">({counts[t] ?? 0})</span>
                  </button>
                ))
              : null}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <RequestIdBadge requestId={requestId} />
            <label className="flex items-center gap-2 text-sm text-ink">
              <input
                className="checkbox"
                checked={includeDeleted}
                onChange={(e) => {
                  setBulkOpsOpen(false);
                  setSelectedIds([]);
                  setIncludeDeleted(e.target.checked);
                }}
                aria-label="structured_include_deleted"
                type="checkbox"
              />
              {UI_COPY.structuredMemory.includeDeleted}
            </label>
          </div>
        </div>

        {viewMode === "table" ? (
          <>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1 sm:col-span-2">
                <span className="text-xs text-subtext">搜索（q）</span>
                <div className="flex gap-2">
                  <input
                    className="input flex-1"
                    value={searchText}
                    onChange={(e) => setSearchText(e.target.value)}
                    aria-label="structured_search"
                    placeholder="Alice"
                  />
                  <button className="btn btn-secondary" onClick={applySearch} type="button">
                    搜索
                  </button>
                </div>
              </label>
            </div>

            {selectedIds.length > 0 ? (
              <div className="mt-4 text-xs text-subtext">
                已选择 <span className="text-ink">{selectedIds.length}</span> 条（{tableLabel(activeTable)}
                ）。可点击右上角“批量操作” 生成 JSON 并打开 Memory Update。
              </div>
            ) : null}
          </>
        ) : (
          <div className="mt-3 text-xs text-subtext">该视图仅用于编辑人物关系（entity_type=character）。</div>
        )}
      </div>

      {viewMode === "table" ? (
        <>
          <div className="rounded-atelier border border-border bg-canvas p-3">
            {pageQuery.loading ? <div className="text-sm text-subtext">加载中...</div> : null}
            {!pageQuery.loading && items.length === 0 ? <div className="text-sm text-subtext">暂无数据</div> : null}

            {items.length > 0 ? (
              <div className="mt-2 overflow-auto rounded-atelier border border-border">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-surface text-xs text-subtext">
                    <tr>
                      <th className="w-10 p-2">
                        <button
                          className="btn btn-secondary btn-icon"
                          onClick={selectAll}
                          type="button"
                          aria-label="structured_select_all"
                        >
                          ✓
                        </button>
                      </th>
                      <th className="p-2">主字段</th>
                      <th className="p-2">摘要</th>
                      <th className="p-2">状态</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((row) => {
                      const id = readStringField(row, "id");
                      const deletedAt = readStringField(row, "deleted_at");
                      const checked = selectedSet.has(id);

                      let primary = id;
                      let summary = "-";
                      if (activeTable === "entities") {
                        primary = `${readStringField(row, "entity_type")}:${readStringField(row, "name")}`;
                        summary = safeSnippet(readTextField(row, "summary_md"));
                      } else if (activeTable === "relations") {
                        primary = `${readStringField(row, "relation_type")}:${readStringField(row, "from_entity_id")}→${readStringField(row, "to_entity_id")}`;
                        summary = safeSnippet(readTextField(row, "description_md"));
                      } else if (activeTable === "events") {
                        primary = `${readStringField(row, "event_type")}:${readStringField(row, "title") || id}`;
                        summary = safeSnippet(readTextField(row, "content_md"));
                      } else if (activeTable === "foreshadows") {
                        primary = `${readBoolField(row, "resolved") ? "已解决" : "未解决"}:${readStringField(row, "title") || id}`;
                        summary = safeSnippet(readTextField(row, "content_md"));
                      } else if (activeTable === "evidence") {
                        primary = `${readStringField(row, "source_type")}:${readStringField(row, "source_id") || "-"}`;
                        summary = safeSnippet(readTextField(row, "quote_md"));
                      }

                      return (
                        <tr key={id} className="border-t border-border">
                          <td className="p-2">
                            <input
                              className="checkbox"
                              aria-label={`structured_select_${id}`}
                              checked={checked}
                              onChange={(e) => toggleSelected(id, e.target.checked)}
                              type="checkbox"
                            />
                          </td>
                          <td className="p-2">
                            <div className="truncate text-ink">{primary}</div>
                            <div className="mt-1 truncate text-[11px] text-subtext">{id}</div>
                          </td>
                          <td className="p-2">
                            <div className="max-w-[520px] truncate text-subtext">{summary}</div>
                          </td>
                          <td className="p-2">
                            {deletedAt ? (
                              <span className="inline-flex rounded bg-danger/10 px-2 py-0.5 text-[11px] text-danger">
                                已删除
                              </span>
                            ) : (
                              <span className="inline-flex rounded bg-success/10 px-2 py-0.5 text-[11px] text-success">
                                正常
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : null}

            {cursor ? (
              <div className="mt-3 flex justify-center">
                <button className="btn btn-secondary" onClick={() => void loadMore()} type="button">
                  加载更多
                </button>
              </div>
            ) : null}
          </div>

          <DebugDetails title={UI_COPY.help.title}>
            <div className="grid gap-2 text-xs text-subtext">
              <div>{UI_COPY.structuredMemory.usageHint}</div>
              <div>{UI_COPY.structuredMemory.exampleHint}</div>
              {projectId ? (
                <div>
                  常用入口：从{" "}
                  <Link className="underline" to={`/projects/${projectId}/writing`}>
                    写作页
                  </Link>{" "}
                  或{" "}
                  <Link className="underline" to={`/projects/${projectId}/chapter-analysis`}>
                    章节分析
                  </Link>{" "}
                  触发“Memory Update”，再在{" "}
                  <Link className="underline" to={`/projects/${projectId}/tasks`}>
                    任务中心
                  </Link>{" "}
                  追踪 ChangeSet/任务状态。
                </div>
              ) : null}
              <div>{UI_COPY.structuredMemory.bulkOpsHint}</div>
              <div className="text-amber-700 dark:text-amber-300">{UI_COPY.structuredMemory.bulkOpsRisk}</div>
            </div>
          </DebugDetails>

          <Drawer
            open={bulkOpsOpen}
            onClose={() => setBulkOpsOpen(false)}
            ariaLabelledBy="structured_bulk_ops_title"
            panelClassName="h-full w-full max-w-[860px] overflow-hidden border-l border-border bg-surface shadow-sm"
          >
            <div className="flex h-full flex-col">
              <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
                <div className="min-w-0">
                  <div className="truncate text-sm text-ink" id="structured_bulk_ops_title">
                    批量操作
                  </div>
                  <div className="mt-0.5 truncate text-xs text-subtext">
                    已选择 {selectedIds.length} 条（{tableLabel(activeTable)}）
                  </div>
                </div>
                <button
                  className="btn btn-secondary"
                  aria-label="关闭"
                  onClick={() => setBulkOpsOpen(false)}
                  type="button"
                >
                  关闭
                </button>
              </div>

              <div className="flex-1 overflow-auto p-4">
                {selectedIds.length === 0 ? (
                  <div className="text-sm text-subtext">请先在表格中选择条目。</div>
                ) : (
                  <div className="grid gap-3">
                    <div className="rounded-atelier border border-border bg-surface p-3">
                      <div className="text-xs text-subtext">1）选择条目</div>
                      <div className="mt-1 text-sm text-ink">
                        已选择 {selectedIds.length} 条（{tableLabel(activeTable)}）
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <button className="btn btn-secondary" onClick={selectAll} type="button">
                          全选当前页
                        </button>
                        <button className="btn btn-secondary" onClick={clearSelected} type="button">
                          清空选择
                        </button>
                      </div>
                    </div>

                    <div className="rounded-atelier border border-border bg-surface p-3">
                      <div className="text-xs text-subtext">2）生成操作</div>
                      <div className="mt-1 text-xs text-subtext">删除操作：{selectedIds.length} 条</div>
                      {activeTable === "foreshadows" ? (
                        <div className="mt-1 text-xs text-subtext">标记已解决：{selectedIds.length} 条（可选）</div>
                      ) : null}
                    </div>

                    <div className="rounded-atelier border border-border bg-surface p-3">
                      <div className="text-xs text-subtext">3）复制并打开 Memory Update</div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <button
                          className="btn btn-secondary"
                          onClick={() => void copyText(generatedDeleteOpsJson, "删除操作 JSON")}
                          type="button"
                        >
                          {UI_COPY.structuredMemory.copyDeleteOps}
                        </button>
                        {activeTable === "foreshadows" ? (
                          <button
                            className="btn btn-secondary"
                            onClick={() => void copyText(generatedResolvedOpsJson, "标记已解决 JSON")}
                            type="button"
                          >
                            {UI_COPY.structuredMemory.copyResolvedOps}
                          </button>
                        ) : null}
                        <button
                          className="btn btn-secondary"
                          disabled={!chapterId}
                          title={chapterId ? undefined : "建议从写作页带上 ?chapterId=... 打开以便 Apply"}
                          onClick={() => {
                            setBulkOpsOpen(false);
                            setMemoryUpdateOpen(true);
                          }}
                          type="button"
                        >
                          打开 Memory Update
                        </button>
                      </div>

                      <details className="mt-3 rounded-atelier border border-border bg-canvas p-3">
                        <summary className="cursor-pointer select-none text-xs text-ink">查看 JSON（高级）</summary>
                        <div className="mt-3 grid gap-2">
                          <div className="text-xs text-subtext">{UI_COPY.structuredMemory.deleteOpsLabel}</div>
                          <textarea
                            className="textarea font-mono text-xs"
                            readOnly
                            rows={Math.min(10, Math.max(3, selectedIds.length + 1))}
                            value={generatedDeleteOpsJson}
                          />
                          {activeTable === "foreshadows" ? (
                            <>
                              <div className="text-xs text-subtext">{UI_COPY.structuredMemory.resolvedOpsLabel}</div>
                              <textarea
                                className="textarea font-mono text-xs"
                                readOnly
                                rows={Math.min(10, Math.max(3, selectedIds.length + 1))}
                                value={generatedResolvedOpsJson}
                              />
                            </>
                          ) : null}
                        </div>
                      </details>

                      <div className="mt-3 rounded-atelier border border-border bg-canvas p-3 text-xs text-subtext">
                        <div>{UI_COPY.structuredMemory.bulkOpsHint}</div>
                        <div className="mt-1">{UI_COPY.structuredMemory.bulkOpsRisk}</div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </Drawer>
        </>
      ) : (
        <CharacterRelationsView
          projectId={projectId}
          chapterId={chapterId}
          focusRelationId={focusRelationId}
          includeDeleted={includeDeleted}
          onRequestId={setRequestId}
        />
      )}

      <MemoryUpdateDrawer
        open={memoryUpdateOpen}
        onClose={() => setMemoryUpdateOpen(false)}
        projectId={projectId}
        chapterId={chapterId}
      />
    </DebugPageShell>
  );
}
