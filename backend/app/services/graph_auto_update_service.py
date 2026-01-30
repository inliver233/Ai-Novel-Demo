from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging import exception_log_fields, log_event
from app.db.session import SessionLocal
from app.db.utils import new_id, utc_now
from app.models.chapter import Chapter
from app.models.llm_preset import LLMPreset
from app.models.project import Project
from app.models.project_task import ProjectTask
from app.models.structured_memory import MemoryEntity, RECOMMENDED_RELATION_TYPES, RELATION_ATTRIBUTES_SCHEMA_V1
from app.schemas.memory_update import MAX_OPS_V1, MemoryUpdateV1Request
from app.services.generation_service import call_llm_and_record, prepare_llm_call, with_param_overrides
from app.services.llm_key_resolver import resolve_api_key_for_project
from app.services.memory_update_service import propose_chapter_memory_change_set
from app.services.output_contracts import contract_for_task

logger = logging.getLogger("ainovel")


GRAPH_AUTO_UPDATE_KIND = "graph_auto_update"

_MAX_EXISTING_ENTITIES_IN_PROMPT = 200
_MAX_CHAPTER_CHARS = 40000
_ID_POOL_SIZE = 24


def _compact_json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


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
    We restrict target_table to: entities / relations / evidence.
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
        f"- ops 必须是非空数组，且长度 <= {MAX_OPS_V1}\n"
        "- 只允许 target_table: entities | relations | evidence（不要输出 events/foreshadows）\n"
        "- op=upsert 时 after 必填；op=delete 时 target_id 必填且 after 必须为 null\n"
        "- 不要捏造信息：信息不足则宁可少写\n"
        "\n"
        "关系类型规范：\n"
        "- relation_type 优先使用推荐集合（见 user 输入）；若确需自定义，使用 snake_case 且语义清晰。\n"
        "\n"
        "证据与引用：\n"
        "- 对每条关键关系，尽量提供 evidence：新增 evidence(op=upsert,target_table=evidence) 并在对应实体/关系 op 的 evidence_ids 引用。\n"
        "- evidence.after.source_type 固定为 \"chapter\"，source_id 固定为本章 chapter_id。\n"
        "- evidence.after.quote_md 放入本章原文的关键片段（Markdown 允许）。\n"
        "\n"
        "ID 规则（非常重要）：\n"
        "- 你只能使用 existing_entities 列表中的 entity_id，或使用 new_entity_id_pool 里的新 entity_id。\n"
        "- 你只能使用 new_evidence_id_pool 里的 evidence_id（用于 evidence 的 target_id，并被 evidence_ids 引用）。\n"
        "- 不要自行编造任何 id（避免与既有数据冲突）。\n"
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
    - Calls LLM to generate a MemoryUpdateV1Request (entities/relations/evidence only)
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

        preset = db.get(LLMPreset, pid)
        if preset is None:
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

        resolved_api_key = resolve_api_key_for_project(db, project=project, user_id=actor, header_api_key=None)
        llm_call = prepare_llm_call(preset)
    except Exception as exc:
        return {"ok": False, "project_id": pid, "reason": "prepare_failed", "error_type": type(exc).__name__}
    finally:
        db.close()

    if llm_call is None:
        return {"ok": False, "project_id": pid, "reason": "llm_call_prepare_failed"}
    if not prompt_system.strip() and not prompt_user.strip():
        return {"ok": False, "project_id": pid, "reason": "prompt_empty"}

    try:
        llm_call2 = with_param_overrides(llm_call, {"temperature": 0.2, "max_tokens": 2048})
        recorded = call_llm_and_record(
            logger=logger,
            request_id=req,
            actor_user_id=actor,
            project_id=pid,
            chapter_id=cid,
            run_type="graph_auto_update_auto_propose",
            api_key=str(resolved_api_key),
            prompt_system=prompt_system,
            prompt_user=prompt_user,
            llm_call=llm_call2,
            run_params_extra_json={
                "task": GRAPH_AUTO_UPDATE_KIND,
                "schema_version": "memory_update_v1",
                "chapter_id": cid,
            },
        )
    except Exception as exc:
        log_event(
            logger,
            "warning",
            event="GRAPH_AUTO_UPDATE_LLM_ERROR",
            project_id=pid,
            chapter_id=cid,
            error_type=type(exc).__name__,
            **exception_log_fields(exc),
        )
        return {"ok": False, "project_id": pid, "chapter_id": cid, "reason": "llm_call_failed", "error_type": type(exc).__name__}

    contract = contract_for_task("memory_update")
    parsed = contract.parse(recorded.text, finish_reason=recorded.finish_reason)
    if parsed.parse_error is not None:
        return {
            "ok": False,
            "project_id": pid,
            "chapter_id": cid,
            "reason": "parse_failed",
            "run_id": recorded.run_id,
            "finish_reason": recorded.finish_reason,
            "warnings": parsed.warnings,
            "parse_error": parsed.parse_error,
        }

    ops = list(parsed.data.get("ops") or [])
    allowed_tables = {"entities", "relations", "evidence"}
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
            "error_type": type(exc).__name__,
        }
    finally:
        db2.close()

    return {
        "ok": True,
        "project_id": pid,
        "chapter_id": cid,
        "run_id": recorded.run_id,
        "finish_reason": recorded.finish_reason,
        "warnings": parsed.warnings,
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

