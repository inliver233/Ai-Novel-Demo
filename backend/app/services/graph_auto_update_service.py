from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.logging import exception_log_fields, log_event
from app.db.session import SessionLocal
from app.db.utils import new_id, utc_now
from app.models.chapter import Chapter
from app.models.llm_preset import LLMPreset
from app.models.project import Project
from app.models.project_task import ProjectTask
from app.models.structured_memory import (
    ENTITY_ATTRIBUTES_SCHEMA_V1,
    MemoryEntity,
    RECOMMENDED_RELATION_TYPES,
    RELATION_ATTRIBUTES_SCHEMA_V1,
    RELATION_TYPE_HINTS_V1,
)
from app.schemas.memory_update import MAX_OPS_V1, MemoryUpdateV1Request
from app.services.generation_service import prepare_llm_call
from app.services.json_repair_service import repair_json_once
from app.services.llm_key_resolver import resolve_api_key_for_project
from app.services.llm_task_preset_resolver import resolve_task_llm_config
from app.services.llm_retry import (
    LlmRetryExhausted,
    call_llm_and_record_with_retries,
    task_llm_max_attempts,
    task_llm_retry_base_seconds,
    task_llm_retry_jitter,
    task_llm_retry_max_seconds,
)
from app.services.memory_update_service import propose_chapter_memory_change_set
from app.services.output_contracts import contract_for_task

logger = logging.getLogger("ainovel")


GRAPH_AUTO_UPDATE_KIND = "graph_auto_update"

_MAX_EXISTING_ENTITIES_IN_PROMPT = 200
_MAX_CHAPTER_CHARS = 40000
_ID_POOL_SIZE = 24

_SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _compact_json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _resolve_graph_llm_call(
    *,
    db: Session,
    project: Project,
    actor_user_id: str,
) -> tuple[object, str] | None:
    missing_key_exc: AppError | None = None
    try:
        resolved_task = resolve_task_llm_config(
            db,
            project=project,
            user_id=actor_user_id,
            task_key=GRAPH_AUTO_UPDATE_KIND,
            header_api_key=None,
        )
    except OperationalError:
        resolved_task = None
    except AppError as exc:
        if str(exc.code or "") != "LLM_KEY_MISSING":
            raise
        missing_key_exc = exc
        resolved_task = None

    if resolved_task is not None:
        return resolved_task.llm_call, str(resolved_task.api_key)

    preset = db.get(LLMPreset, project.id)
    if preset is None:
        if missing_key_exc is not None:
            raise missing_key_exc
        return None

    api_key = resolve_api_key_for_project(db, project=project, user_id=actor_user_id, header_api_key=None)
    return prepare_llm_call(preset), str(api_key)


def _truncate(text: str | None, *, limit: int) -> str:
    raw = str(text or "")
    if len(raw) <= limit:
        return raw
    return raw[:limit]


def memory_update_changeset_key_from_task_idempotency_key(task_key: str) -> str:
    """
    Returns a <=64 chars idempotency key for MemoryUpdateV1Request derived from ProjectTask.idempotency_key.
    """
    raw = str(task_key or "").strip()
    if not raw:
        return f"graphupd-{new_id()[:12]}"
    import hashlib

    h = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"graphupd-{h}"


def build_graph_auto_update_prompt_v1(
    *,
    project_id: str,
    chapter: Chapter,
    existing_entities: list[dict[str, Any]],
    new_entity_id_pool: list[str],
    new_evidence_id_pool: list[str],
    focus: str | None,
) -> tuple[str, str]:
    """
    Prompt contract (v1):

    Output must conform to `memory_update_v1` JSON contract (ops list).
    We restrict target_table to: entities / relations / events / evidence.
    """

    pid = str(project_id or "").strip()
    cid = str(getattr(chapter, "id", "") or "").strip()
    focus_text = (focus or "").strip()

    system = (
        "你是小说写作助手，负责在章节定稿后，把本章中涉及的人物/组织/地点等实体与人物关系抽取为「结构化记忆-图谱底座」。\n"
        "你必须只输出一个 JSON object（允许使用 ```json 代码块包裹）。不要输出任何其它文字。\n"
        "schema: memory_update_v1\n"
        "\n"
        "输出必须是一个 JSON object：\n"
        "{\n"
        '  "title": "简短标题",\n'
        '  "summary_md": "可选：用 Markdown 简述本次更新意图",\n'
        '  "ops": [ { ... } ]\n'
        "}\n"
        "\n"
        "规则：\n"
        f"- ops 必须是数组（允许为空数组，当本章没有明确可抽取更新时），且长度 <= {MAX_OPS_V1}\n"
        "- 只允许 target_table: entities | relations | events | evidence（不要输出 foreshadows）\n"
        "- op=upsert 时 after 必填；op=delete 时 target_id 必填且 after 必须为 null\n"
        "- 不要捏造信息：信息不足则宁可少写\n"
        "\n"
        "关系类型规范：\n"
        "- relation_type 优先使用推荐集合（见 user 输入）；若确需自定义，使用 snake_case 且语义清晰。\n"
        "- 对有方向性的关系（如 owes/leader_of 等），请遵循 user 输入中的 direction hints。\n"
        "\n"
        "属性字段规范：\n"
        "- entities.after.attributes / relations.after.attributes 只使用 user 输入中 schema_v1 列出的 keys（其余不要输出）。\n"
        "- 若关系涉及明确的具体事件（如 betrayed/owes/protects），可在 relations.after.attributes.context_md 写入 1~3 句语境摘要（配合 evidence 回放）。\n"
        "\n"
        "证据与引用：\n"
        "- 对每条关键关系，尽量提供 evidence：新增 evidence(op=upsert,target_table=evidence) 并在对应实体/关系 op 的 evidence_ids 引用。\n"
        "- evidence.after.source_type 固定为 \"chapter\"，source_id 固定为本章 chapter_id。\n"
        "- evidence.after.quote_md 放入本章原文的关键片段（Markdown 允许）。\n"
        "\n"
        "ID 规则（非常重要）：\n"
        "- existing_entities 的字段名是 id（不是 entity_id）。你只能使用 existing_entities[].id 或 new_entity_id_pool 里的新 id。\n"
        "- 你只能使用 new_evidence_id_pool 里的 id（用于 evidence 的 target_id，并被 evidence_ids 引用）。\n"
        "- 不要自行编造任何 id（避免与既有数据冲突）。\n"
        "\n"
        "字段名示例（非常重要；不要输出 from_id/to_id/entity_id 等错误字段）：\n"
        "- entities.after: {entity_type,name,summary_md,attributes}\n"
        "- relations.after: {from_entity_id,to_entity_id,relation_type,description_md,attributes}\n"
        "- events.after: {chapter_id,event_type,title,content_md,attributes}\n"
        "- evidence.after: {source_type:'chapter',source_id:chapter_id,quote_md,attributes}\n"
        "\n"
        "示例（relation upsert）：\n"
        "{\n"
        '  \"op\": \"upsert\",\n'
        '  \"target_table\": \"relations\",\n'
        '  \"target_id\": null,\n'
        '  \"after\": {\n'
        '    \"from_entity_id\": \"<use existing_entities[].id or new_entity_id_pool>\",\n'
        '    \"to_entity_id\": \"<use existing_entities[].id or new_entity_id_pool>\",\n'
        '    \"relation_type\": \"friend\",\n'
        '    \"description_md\": \"...\",\n'
        '    \"attributes\": {}\n'
        "  },\n"
        '  \"evidence_ids\": [\"<use new_evidence_id_pool>\"]\n'
        "}\n"
    )

    user = (
        f"project_id: {pid}\n"
        f"chapter_id: {cid}\n"
        f"chapter_number: {int(getattr(chapter, 'number', 0) or 0)}\n"
        f"chapter_title: {str(getattr(chapter, 'title', '') or '')}\n\n"
        "=== focus (optional) ===\n"
        f"{focus_text}\n\n"
        "=== relation_type_recommended ===\n"
        f"{_compact_json_dumps(list(RECOMMENDED_RELATION_TYPES))}\n\n"
        "=== relation_type_hints_v1 (direction guidance; optional) ===\n"
        f"{_compact_json_dumps(RELATION_TYPE_HINTS_V1)}\n\n"
        "=== entity_attributes_schema_v1 (suggested keys; not enforced) ===\n"
        f"{_compact_json_dumps(ENTITY_ATTRIBUTES_SCHEMA_V1)}\n\n"
        "=== relation_attributes_schema_v1 (suggested keys; not enforced) ===\n"
        f"{_compact_json_dumps(RELATION_ATTRIBUTES_SCHEMA_V1)}\n\n"
        "=== existing_entities (id + name) ===\n"
        f"{_compact_json_dumps(existing_entities)}\n\n"
        "=== new_entity_id_pool (use for new entities) ===\n"
        f"{_compact_json_dumps(new_entity_id_pool)}\n\n"
        "=== new_evidence_id_pool (use for new evidence) ===\n"
        f"{_compact_json_dumps(new_evidence_id_pool)}\n\n"
        "=== chapter_plan ===\n"
        f"{str(getattr(chapter, 'plan', '') or '')}\n\n"
        "=== chapter_content_md ===\n"
        f"{_truncate(str(getattr(chapter, 'content_md', '') or ''), limit=_MAX_CHAPTER_CHARS)}\n"
    )

    return system, user


def _filter_attributes(
    attributes: object,
    *,
    allowed_keys: set[str],
) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(attributes, dict):
        return None, []
    kept: dict[str, Any] = {}
    dropped: list[str] = []
    for k, v in attributes.items():
        key = str(k or "").strip()
        if not key:
            continue
        if key in allowed_keys:
            kept[key] = v
        else:
            dropped.append(key)
    return (kept if kept else None), dropped


def graph_auto_update_v1(
    *,
    project_id: str,
    actor_user_id: str,
    request_id: str,
    chapter_id: str,
    change_set_idempotency_key: str,
    focus: str | None,
) -> dict[str, Any]:
    """
    Fail-soft AI propose:
    - Calls LLM to generate a MemoryUpdateV1Request (entities/relations/events/evidence)
    - Proposes a MemoryChangeSet for the chapter (apply/rollback supported)
    """

    pid = str(project_id or "").strip()
    cid = str(chapter_id or "").strip()
    actor = str(actor_user_id or "").strip()
    req = str(request_id or "").strip() or f"graph_auto_update:{new_id()}"
    idem = str(change_set_idempotency_key or "").strip()

    if not pid:
        return {"ok": False, "reason": "project_id_empty"}
    if not cid:
        return {"ok": False, "project_id": pid, "reason": "chapter_id_empty"}
    if not actor:
        return {"ok": False, "project_id": pid, "reason": "actor_user_id_missing"}
    if len(idem) < 8 or len(idem) > 64:
        return {"ok": False, "project_id": pid, "reason": "idempotency_key_invalid"}

    resolved_api_key = ""
    prompt_system = ""
    prompt_user = ""
    llm_call = None

    db = SessionLocal()
    try:
        project = db.get(Project, pid)
        if project is None:
            return {"ok": False, "project_id": pid, "reason": "project_not_found"}

        chapter = db.get(Chapter, cid)
        if chapter is None or str(getattr(chapter, "project_id", "")) != pid:
            return {"ok": False, "project_id": pid, "chapter_id": cid, "reason": "chapter_not_found"}
        if str(getattr(chapter, "status", "") or "") != "done":
            return {"ok": False, "project_id": pid, "chapter_id": cid, "reason": "chapter_not_done"}

        resolved = _resolve_graph_llm_call(db=db, project=project, actor_user_id=actor)
        if resolved is None:
            return {"ok": False, "project_id": pid, "reason": "llm_preset_missing"}

        # Existing entities help the model refer to stable IDs for relations.
        rows = (
            db.execute(
                select(MemoryEntity)
                .where(
                    MemoryEntity.project_id == pid,
                    MemoryEntity.deleted_at.is_(None),
                )
                .order_by(MemoryEntity.updated_at.desc(), MemoryEntity.id.desc())
                .limit(_MAX_EXISTING_ENTITIES_IN_PROMPT)
            )
            .scalars()
            .all()
        )
        existing_entities = [
            {
                "id": str(r.id),
                "entity_type": str(r.entity_type or "generic"),
                "name": str(r.name or ""),
            }
            for r in rows
            if str(getattr(r, "id", "") or "").strip() and str(getattr(r, "name", "") or "").strip()
        ]

        new_entity_id_pool = [new_id() for _ in range(_ID_POOL_SIZE)]
        new_evidence_id_pool = [new_id() for _ in range(_ID_POOL_SIZE)]

        prompt_system, prompt_user = build_graph_auto_update_prompt_v1(
            project_id=pid,
            chapter=chapter,
            existing_entities=existing_entities,
            new_entity_id_pool=new_entity_id_pool,
            new_evidence_id_pool=new_evidence_id_pool,
            focus=focus,
        )

        llm_call, resolved_api_key = resolved
    except Exception as exc:
        return {"ok": False, "project_id": pid, "reason": "prepare_failed", "error_type": type(exc).__name__}
    finally:
        db.close()

    if llm_call is None:
        return {"ok": False, "project_id": pid, "reason": "llm_call_prepare_failed"}
    if not prompt_system.strip() and not prompt_user.strip():
        return {"ok": False, "project_id": pid, "reason": "prompt_empty"}

    llm_attempts: list[dict[str, Any]] = []
    try:
        base_max_tokens = llm_call.params.get("max_tokens")

        def _clamp_max_tokens(limit: int) -> int:
            if isinstance(base_max_tokens, int) and base_max_tokens > 0:
                return min(int(limit), int(base_max_tokens))
            return int(limit)

        retry_system = (
            prompt_system
            + "\n"
            + "【重试模式】上一轮调用失败/超时。请输出更短、更保守的图谱更新提议：\n"
            + "- 只输出裸 JSON（不要 Markdown，不要代码块）\n"
            + "- ops 数量 <= 32；只抽取最确定的实体/关系/证据，不要穷举\n"
            + "- 严格遵守 memory_update_v1 字段名（target_table/target_id/after/evidence_ids 等）\n"
        )

        max_attempts = task_llm_max_attempts(default=3)
        recorded, llm_attempts = call_llm_and_record_with_retries(
            logger=logger,
            request_id=req,
            actor_user_id=actor,
            project_id=pid,
            chapter_id=cid,
            run_type="graph_auto_update_auto_propose",
            api_key=str(resolved_api_key),
            prompt_system=prompt_system,
            prompt_user=prompt_user,
            llm_call=llm_call,
            run_params_extra_json={
                "task": GRAPH_AUTO_UPDATE_KIND,
                "schema_version": "memory_update_v1",
                "chapter_id": cid,
            },
            max_attempts=max_attempts,
            retry_prompt_system=retry_system,
            llm_call_overrides_by_attempt={
                1: {"temperature": 0.2, "max_tokens": _clamp_max_tokens(2048)},
                2: {"temperature": 0.1, "max_tokens": _clamp_max_tokens(1024)},
                3: {"temperature": 0.0, "max_tokens": _clamp_max_tokens(512)},
            },
            backoff_base_seconds=task_llm_retry_base_seconds(),
            backoff_max_seconds=task_llm_retry_max_seconds(),
            jitter=task_llm_retry_jitter(),
        )
    except LlmRetryExhausted as exc:
        log_event(
            logger,
            "warning",
            event="GRAPH_AUTO_UPDATE_LLM_ERROR",
            project_id=pid,
            chapter_id=cid,
            run_id=exc.run_id,
            error_type=str(exc.error_type),
            **exception_log_fields(exc.last_exception),
        )
        return {
            "ok": False,
            "project_id": pid,
            "chapter_id": cid,
            "reason": "llm_call_failed",
            "run_id": exc.run_id,
            "error_type": exc.error_type,
            "error_message": exc.error_message[:400],
            "attempts": list(exc.attempts or []),
            "error": {
                "code": exc.error_code or "LLM_CALL_FAILED",
                "details": {"attempts": list(exc.attempts or [])},
            },
        }

    contract = contract_for_task("memory_update")
    parsed = contract.parse(recorded.text, finish_reason=recorded.finish_reason)
    repair_run_id: str | None = None
    warnings = list(parsed.warnings or [])
    if len(list(llm_attempts or [])) >= 2:
        warnings.append("llm_retry_used")
    if parsed.parse_error is not None:
        repair_schema = (
            "{\n"
            '  "title": string | null,\n'
            '  "summary_md": string | null,\n'
            '  "ops": [\n'
            "    {\n"
            '      "op": "upsert" | "delete",\n'
            '      "target_table": "entities" | "relations" | "events" | "evidence",\n'
            '      "target_id": string | null,\n'
            '      "after": object | null,\n'
            '      "evidence_ids": [string]\n'
            "    }\n"
            "  ]\n"
            "}\n"
        )

        repair_req = f"{req}:repair"
        if len(repair_req) > 64:
            repair_req = repair_req[:64]
        repair = repair_json_once(
            request_id=repair_req,
            actor_user_id=actor,
            project_id=pid,
            chapter_id=cid,
            api_key=str(resolved_api_key),
            llm_call=llm_call,
            raw_output=recorded.text,
            schema=repair_schema,
            expected_root="object",
            origin_run_id=recorded.run_id,
            origin_task=GRAPH_AUTO_UPDATE_KIND,
        )
        repair_run_id = str(repair.get("repair_run_id") or "").strip() or None
        warnings.extend(list(repair.get("warnings") or []))

        if bool(repair.get("ok")) and isinstance(repair.get("value"), dict):
            repaired_text = str(repair.get("raw_json") or "").strip()
            parsed2 = contract.parse(repaired_text, finish_reason=str(repair.get("finish_reason") or "").strip() or None)
            if parsed2.parse_error is None:
                parsed = parsed2
            else:
                parse_error = parsed2.parse_error if isinstance(parsed2.parse_error, dict) else {"message": str(parsed2.parse_error or "")}
                if isinstance(parse_error, dict):
                    parse_error = dict(parse_error)
                    if repair_run_id:
                        parse_error["repair_run_id"] = repair_run_id
                    parse_error["original_parse_error"] = parsed.parse_error
                return {
                    "ok": False,
                    "project_id": pid,
                    "chapter_id": cid,
                    "reason": "parse_failed",
                    "run_id": recorded.run_id,
                    "repair_run_id": repair_run_id,
                    "finish_reason": recorded.finish_reason,
                    "warnings": warnings,
                    "parse_error": parse_error,
                }
        else:
            parse_error = parsed.parse_error if isinstance(parsed.parse_error, dict) else {"message": str(parsed.parse_error or "")}
            if isinstance(parse_error, dict):
                parse_error = dict(parse_error)
                if repair_run_id:
                    parse_error["repair_run_id"] = repair_run_id
                if repair.get("reason"):
                    parse_error["repair_reason"] = repair.get("reason")
                if repair.get("parse_error"):
                    parse_error["repair_parse_error"] = repair.get("parse_error")
                if repair.get("error_message"):
                    parse_error["repair_error_message"] = repair.get("error_message")
            return {
                "ok": False,
                "project_id": pid,
                "chapter_id": cid,
                "reason": "parse_failed",
                "run_id": recorded.run_id,
                "repair_run_id": repair_run_id,
                "finish_reason": recorded.finish_reason,
                "warnings": warnings,
                "parse_error": parse_error,
            }

    ops = list(parsed.data.get("ops") or [])
    if not ops:
        warnings.append("graph_auto_update_noop")
        return {
            "ok": True,
            "project_id": pid,
            "chapter_id": cid,
            "run_id": recorded.run_id,
            "repair_run_id": repair_run_id,
            "finish_reason": recorded.finish_reason,
            "warnings": warnings,
            "no_op": True,
        }

    warnings_extra: list[str] = []
    allowed_tables = {"entities", "relations", "events", "evidence"}
    for op in ops:
        if not isinstance(op, dict):
            continue
        target_table = str(op.get("target_table") or "").strip()
        if target_table and target_table not in allowed_tables:
            return {
                "ok": False,
                "project_id": pid,
                "chapter_id": cid,
                "reason": "unsupported_target_table",
                "run_id": recorded.run_id,
                "target_table": target_table,
            }

        after = op.get("after")
        if not isinstance(after, dict):
            continue

        if target_table == "evidence":
            st = str(after.get("source_type") or "").strip()
            if st and st != "chapter":
                return {
                    "ok": False,
                    "project_id": pid,
                    "chapter_id": cid,
                    "reason": "evidence_source_type_mismatch",
                    "run_id": recorded.run_id,
                    "source_type": st,
                }
            if not st:
                after["source_type"] = "chapter"

            sid = str(after.get("source_id") or "").strip()
            if sid and sid != cid:
                return {
                    "ok": False,
                    "project_id": pid,
                    "chapter_id": cid,
                    "reason": "evidence_source_id_mismatch",
                    "run_id": recorded.run_id,
                    "source_id": sid,
                }
            if not sid:
                after["source_id"] = cid

        if target_table == "entities":
            attrs, dropped = _filter_attributes(after.get("attributes"), allowed_keys=set(ENTITY_ATTRIBUTES_SCHEMA_V1.keys()))
            if dropped:
                warnings_extra.append(f"graph_auto_update:dropped_entity_attributes_keys:{sorted(set(dropped))}")
            after["attributes"] = attrs

        if target_table == "relations":
            rtype = str(after.get("relation_type") or "related_to").strip() or "related_to"
            if rtype not in RECOMMENDED_RELATION_TYPES and not _SNAKE_CASE_RE.match(rtype):
                return {
                    "ok": False,
                    "project_id": pid,
                    "chapter_id": cid,
                    "reason": "invalid_relation_type",
                    "run_id": recorded.run_id,
                    "relation_type": rtype,
                }

            attrs, dropped = _filter_attributes(
                after.get("attributes"),
                allowed_keys=set(RELATION_ATTRIBUTES_SCHEMA_V1.keys()),
            )
            if dropped:
                warnings_extra.append(f"graph_auto_update:dropped_relation_attributes_keys:{sorted(set(dropped))}")
            after["attributes"] = attrs

    payload = MemoryUpdateV1Request(
        schema_version="memory_update_v1",
        idempotency_key=idem,
        title=str(parsed.data.get("title") or "Graph Auto Update (auto)").strip() or "Graph Auto Update (auto)",
        summary_md=str(parsed.data.get("summary_md") or "").strip() or None,
        ops=ops,
    )

    db2 = SessionLocal()
    try:
        chapter2 = db2.get(Chapter, cid)
        if chapter2 is None or str(getattr(chapter2, "project_id", "")) != pid:
            return {"ok": False, "project_id": pid, "chapter_id": cid, "reason": "chapter_not_found"}
        proposed = propose_chapter_memory_change_set(
            db=db2,
            request_id=req,
            actor_user_id=actor,
            chapter=chapter2,
            payload=payload,
        )
    except Exception as exc:
        return {
            "ok": False,
            "project_id": pid,
            "chapter_id": cid,
            "reason": "propose_failed",
            "run_id": recorded.run_id,
            "repair_run_id": repair_run_id,
            "error_type": type(exc).__name__,
        }
    finally:
        db2.close()

    return {
        "ok": True,
        "project_id": pid,
        "chapter_id": cid,
        "run_id": recorded.run_id,
        "repair_run_id": repair_run_id,
        "finish_reason": recorded.finish_reason,
        "warnings": [*warnings, *warnings_extra],
        **(proposed if isinstance(proposed, dict) else {"proposed": proposed}),
    }


def schedule_graph_auto_update_task(
    *,
    db: Session | None = None,
    project_id: str,
    actor_user_id: str | None,
    request_id: str | None,
    chapter_id: str,
    chapter_token: str | None,
    focus: str | None,
    reason: str,
) -> str | None:
    """
    Fail-soft scheduler: ensure/enqueue a ProjectTask(kind=graph_auto_update).
    """

    pid = str(project_id or "").strip()
    cid = str(chapter_id or "").strip()
    if not pid or not cid:
        return None

    token_norm = str(chapter_token or "").strip() or utc_now().isoformat().replace("+00:00", "Z")
    chapter_prefix = cid[:12]
    idempotency_key = f"graph_ai:ch:{chapter_prefix}:since:{token_norm}:v1"

    owns_session = db is None
    if db is None:
        db = SessionLocal()
    try:
        task = (
            db.execute(
                select(ProjectTask).where(
                    ProjectTask.project_id == pid,
                    ProjectTask.idempotency_key == idempotency_key,
                )
            )
            .scalars()
            .first()
        )

        if task is None:
            task = ProjectTask(
                id=new_id(),
                project_id=pid,
                actor_user_id=str(actor_user_id or "").strip() or None,
                kind=GRAPH_AUTO_UPDATE_KIND,
                status="queued",
                idempotency_key=idempotency_key,
                params_json=_compact_json_dumps(
                    {
                        "reason": str(reason or "").strip() or "dirty",
                        "request_id": (str(request_id or "").strip() or None),
                        "chapter_id": cid,
                        "chapter_token": token_norm,
                        "focus": (str(focus or "").strip() or None),
                        "change_set_idempotency_key": memory_update_changeset_key_from_task_idempotency_key(idempotency_key),
                        "triggered_at": utc_now().isoformat().replace("+00:00", "Z"),
                    }
                ),
                result_json=None,
                error_json=None,
            )
            db.add(task)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                task = (
                    db.execute(
                        select(ProjectTask).where(
                            ProjectTask.project_id == pid,
                            ProjectTask.idempotency_key == idempotency_key,
                        )
                    )
                    .scalars()
                    .first()
                )

        if task is None:
            return None

        from app.services.task_queue import get_task_queue

        queue = get_task_queue()
        try:
            queue.enqueue(kind="project_task", task_id=str(task.id))
        except Exception as exc:
            fields = exception_log_fields(exc)
            msg = str(fields.get("exception") or str(exc)).replace("\n", " ").strip()[:200]
            task.status = "failed"
            task.finished_at = utc_now()
            task.error_json = _compact_json_dumps({"error_type": type(exc).__name__, "message": msg})
            db.commit()
            log_event(
                logger,
                "warning",
                event="PROJECT_TASK_ENQUEUE_ERROR",
                task_id=str(task.id),
                project_id=str(task.project_id),
                kind=str(task.kind),
                error_type=type(exc).__name__,
                **fields,
            )
        return str(task.id)
    finally:
        if owns_session:
            db.close()
