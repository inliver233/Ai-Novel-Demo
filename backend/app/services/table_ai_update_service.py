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
from app.models.project_table import ProjectTable, ProjectTableRow
from app.models.project_task import ProjectTask
from app.services.generation_service import call_llm_and_record, prepare_llm_call, with_param_overrides
from app.services.llm_key_resolver import resolve_api_key_for_project
from app.services.memory_update_service import propose_project_table_change_set
from app.services.output_parsers import extract_json_value, likely_truncated_json
from app.services.table_executor import MAX_OPS_V1, TableRowOpV1, TableUpdateV1Request, is_key_value_schema

logger = logging.getLogger("ainovel")


TABLE_AI_UPDATE_KIND = "table_ai_update"

_MAX_ROWS_IN_PROMPT = 200
_MAX_CHAPTER_CHARS = 40000


def _compact_json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _safe_json_loads(value: str | None) -> Any | None:
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def _truncate(text: str | None, *, limit: int) -> str:
    raw = str(text or "")
    if len(raw) <= limit:
        return raw
    return raw[:limit]


def _coerce_rows_for_prompt(rows: list[ProjectTableRow]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows[:_MAX_ROWS_IN_PROMPT]:
        data_obj = _safe_json_loads(getattr(r, "data_json", None))
        data = data_obj if isinstance(data_obj, dict) else {}
        out.append(
            {
                "id": str(r.id),
                "row_index": int(getattr(r, "row_index", 0) or 0),
                "data": data,
            }
        )
    return out


def build_table_ai_update_prompt_v1(
    *,
    project_id: str,
    table: ProjectTable,
    schema: dict[str, Any],
    existing_rows: list[dict[str, Any]],
    chapter: Chapter | None,
    focus: str | None,
) -> tuple[str, str]:
    """
    Prompt contract (v1):

    The model must output a single JSON object with:
    {
      "title": "...",
      "summary_md": "...",
      "ops": [ { TableRowOpV1 } ]
    }
    """

    pid = str(project_id or "").strip()
    table_id = str(getattr(table, "id", "") or "").strip()
    table_key = str(getattr(table, "table_key", "") or "").strip()
    table_name = str(getattr(table, "name", "") or "").strip()

    is_kv = is_key_value_schema(schema)
    focus_text = (focus or "").strip()

    chapter_number = int(getattr(chapter, "number", 0) or 0) if chapter is not None else 0
    chapter_title = str(getattr(chapter, "title", "") or "") if chapter is not None else ""
    chapter_plan = str(getattr(chapter, "plan", "") or "") if chapter is not None else ""
    chapter_content = _truncate(getattr(chapter, "content_md", "") if chapter is not None else "", limit=_MAX_CHAPTER_CHARS)

    system = (
        "你是小说写作助手，负责把最新章节内容中的“可数字化状态变化”同步到「数值表格系统」中。\n"
        "你必须只输出一个 JSON object（允许使用 ```json 代码块包裹）。不要输出任何其它文字。\n"
        "schema: table_update_v1\n"
        "输出必须是一个 JSON object：\n"
        "{\n"
        '  "title": "简短标题",\n'
        '  "summary_md": "可选：用 Markdown 简述本次更新意图",\n'
        '  "ops": [ { ... } ]\n'
        "}\n"
        "\n"
        "规则：\n"
        f"- ops 必须是非空数组，且长度 <= {MAX_OPS_V1}\n"
        "- 只能修改给定的 table_id（不要写其它 table_id）\n"
        '- op=upsert 时 data 必填；op=delete 时 row_id 必填且 data 必须为 null\n'
        "- data 必须严格符合 schema.columns（字段名与类型）\n"
        "- 信息不足时宁可少更新，不要捏造\n"
    )

    if is_kv:
        system += (
            "\n"
            "本表为 Key/Value 结构（columns: key,value）。\n"
            "- 你可以省略 upsert 的 row_id：后端会用 data.key 匹配现有行并更新，避免重复 key。\n"
            "- 严禁创建重复 key：同一个 key 只能对应一行。\n"
        )

    user = (
        f"project_id: {pid}\n"
        f"table_id: {table_id}\n"
        f"table_key: {table_key}\n"
        f"table_name: {table_name}\n\n"
        "=== table_schema ===\n"
        f"{_compact_json_dumps(schema if isinstance(schema, dict) else {})}\n\n"
        "=== existing_rows (may be empty) ===\n"
        f"{_compact_json_dumps(existing_rows)}\n\n"
        f"=== focus (optional) ===\n{focus_text}\n\n"
        "=== chapter (optional) ===\n"
        f"chapter_number: {chapter_number}\n"
        f"chapter_title: {chapter_title}\n\n"
        "=== chapter_plan (optional) ===\n"
        f"{chapter_plan}\n\n"
        "=== chapter_content_md (optional) ===\n"
        f"{chapter_content}\n"
    )

    return system, user


def parse_table_update_output_v1(
    text: str, *, expected_table_id: str, finish_reason: str | None = None
) -> tuple[dict[str, Any], list[str], dict[str, Any] | None]:
    warnings: list[str] = []
    value, raw_json = extract_json_value(text)
    if isinstance(value, list):
        value = {"ops": value}
    if not isinstance(value, dict):
        parse_error: dict[str, Any] = {"code": "TABLE_UPDATE_PARSE_ERROR", "message": "无法从模型输出解析 table_update JSON"}
        if likely_truncated_json(text):
            parse_error["hint"] = "输出疑似被截断（JSON 未闭合），可尝试增大 max_tokens 或减少输出长度"
        data = {"title": "", "summary_md": "", "ops": [], "raw_output": text}
        return data, warnings, parse_error

    title = value.get("title")
    title_out = title.strip() if isinstance(title, str) else ""
    summary_md = value.get("summary_md")
    summary_out = summary_md.strip() if isinstance(summary_md, str) else ""

    ops_raw = value.get("ops")
    if not isinstance(ops_raw, list) or not ops_raw:
        data: dict[str, Any] = {"title": title_out, "summary_md": summary_out, "ops": [], "raw_output": text}
        if raw_json:
            data["raw_json"] = raw_json
        return data, warnings, {"code": "TABLE_UPDATE_PARSE_ERROR", "message": "ops 为空或缺失"}

    ops_out: list[dict[str, Any]] = []
    for idx, item in enumerate(ops_raw):
        if not isinstance(item, dict):
            return (
                {"title": title_out, "summary_md": summary_out, "ops": [], "raw_output": text},
                warnings,
                {"code": "TABLE_UPDATE_PARSE_ERROR", "message": f"ops[{idx}] 必须是 object"},
            )
        op_dict = dict(item)
        table_id = str(op_dict.get("table_id") or "").strip()
        if not table_id:
            op_dict["table_id"] = expected_table_id
        elif table_id != expected_table_id:
            return (
                {"title": title_out, "summary_md": summary_out, "ops": [], "raw_output": text},
                warnings,
                {"code": "TABLE_UPDATE_PARSE_ERROR", "message": f"ops[{idx}] table_id 不匹配"},
            )
        try:
            op = TableRowOpV1.model_validate(op_dict)
        except Exception as exc:
            return (
                {"title": title_out, "summary_md": summary_out, "ops": [], "raw_output": text},
                warnings,
                {"code": "TABLE_UPDATE_PARSE_ERROR", "message": f"ops[{idx}] schema invalid:{type(exc).__name__}"},
            )
        ops_out.append(dict(op.model_dump()))

    data = {"title": title_out, "summary_md": summary_out, "ops": ops_out, "raw_output": text}
    if raw_json:
        data["raw_json"] = raw_json
    if finish_reason == "length":
        warnings.append("output_truncated")
    return data, warnings, None


def table_update_changeset_key_from_task_idempotency_key(task_key: str) -> str:
    """
    Returns a <=64 chars idempotency key for TableUpdateV1Request derived from ProjectTask.idempotency_key.
    """
    raw = str(task_key or "").strip()
    if not raw:
        return f"tblupd-{new_id()[:12]}"
    digest = _compact_json_dumps(raw)
    # keep deterministic without leaking secrets: use a stable short hash of the task key
    import hashlib

    h = hashlib.sha1(digest.encode("utf-8")).hexdigest()[:16]
    return f"tblupd-{h}"


def table_ai_update_v1(
    *,
    project_id: str,
    actor_user_id: str,
    request_id: str,
    table_id: str,
    change_set_idempotency_key: str,
    chapter_id: str | None,
    focus: str | None,
) -> dict[str, Any]:
    """
    Fail-soft AI propose:
    - Calls LLM to generate a TableUpdateV1Request (ops only)
    - Proposes a MemoryChangeSet for project_table_rows (apply/rollback supported)
    """

    pid = str(project_id or "").strip()
    tid = str(table_id or "").strip()
    actor = str(actor_user_id or "").strip()
    req = str(request_id or "").strip() or f"table_ai_update:{new_id()}"
    chapter_id_norm = str(chapter_id or "").strip() or None
    idem = str(change_set_idempotency_key or "").strip()

    if not pid:
        return {"ok": False, "reason": "project_id_empty"}
    if not tid:
        return {"ok": False, "project_id": pid, "reason": "table_id_empty"}
    if not actor:
        return {"ok": False, "project_id": pid, "reason": "actor_user_id_missing"}
    if len(idem) < 8 or len(idem) > 64:
        return {"ok": False, "project_id": pid, "reason": "idempotency_key_invalid"}

    resolved_api_key = ""
    prompt_system = ""
    prompt_user = ""
    llm_call = None
    schema_dict: dict[str, Any] = {}
    table_name = ""
    chapter_id_effective: str | None = None
    existing_rows: list[dict[str, Any]] = []

    db = SessionLocal()
    try:
        project = db.get(Project, pid)
        if project is None:
            return {"ok": False, "project_id": pid, "reason": "project_not_found"}

        table = db.get(ProjectTable, tid)
        if table is None or str(getattr(table, "project_id", "")) != pid:
            return {"ok": False, "project_id": pid, "table_id": tid, "reason": "table_not_found"}
        table_name = str(getattr(table, "name", "") or "").strip()

        chapter: Chapter | None = None
        if chapter_id_norm:
            chapter = db.get(Chapter, chapter_id_norm)
            if chapter is None or str(getattr(chapter, "project_id", "")) != pid:
                return {"ok": False, "project_id": pid, "table_id": tid, "reason": "chapter_not_found"}
            chapter_id_effective = str(getattr(chapter, "id", "") or "").strip() or None
        else:
            chapter = (
                db.execute(
                    select(Chapter)
                    .where(
                        Chapter.project_id == pid,
                        Chapter.status == "done",
                    )
                    .order_by(Chapter.updated_at.desc(), Chapter.id.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
            chapter_id_effective = str(getattr(chapter, "id", "") or "").strip() or None

        rows = (
            db.execute(
                select(ProjectTableRow)
                .where(ProjectTableRow.project_id == pid, ProjectTableRow.table_id == tid)
                .order_by(ProjectTableRow.row_index.asc(), ProjectTableRow.id.asc())
                .limit(_MAX_ROWS_IN_PROMPT)
            )
            .scalars()
            .all()
        )
        existing_rows = _coerce_rows_for_prompt(rows)

        schema_obj = _safe_json_loads(str(getattr(table, "schema_json", "") or ""))
        schema_dict = schema_obj if isinstance(schema_obj, dict) else {}

        preset = db.get(LLMPreset, pid)
        if preset is None:
            return {"ok": False, "project_id": pid, "reason": "llm_preset_missing"}

        resolved_api_key = resolve_api_key_for_project(db, project=project, user_id=actor, header_api_key=None)
        llm_call = prepare_llm_call(preset)
        prompt_system, prompt_user = build_table_ai_update_prompt_v1(
            project_id=pid,
            table=table,
            schema=schema_dict,
            existing_rows=existing_rows,
            chapter=chapter,
            focus=focus,
        )
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
            chapter_id=chapter_id_effective,
            run_type="table_ai_update_auto_propose",
            api_key=str(resolved_api_key),
            prompt_system=prompt_system,
            prompt_user=prompt_user,
            llm_call=llm_call2,
            run_params_extra_json={
                "task": TABLE_AI_UPDATE_KIND,
                "schema_version": "table_update_v1",
                "table_id": tid,
                "table_name": table_name,
                "kv_mode": bool(is_key_value_schema(schema_dict)),
                "rows_in_prompt": int(len(existing_rows)),
            },
        )
    except Exception as exc:
        log_event(
            logger,
            "warning",
            event="TABLE_AI_UPDATE_LLM_ERROR",
            project_id=pid,
            table_id=tid,
            error_type=type(exc).__name__,
            **exception_log_fields(exc),
        )
        return {"ok": False, "project_id": pid, "table_id": tid, "reason": "llm_call_failed", "error_type": type(exc).__name__}

    parsed, warnings, parse_error = parse_table_update_output_v1(
        recorded.text, expected_table_id=tid, finish_reason=recorded.finish_reason
    )
    if parse_error is not None:
        return {
            "ok": False,
            "project_id": pid,
            "table_id": tid,
            "reason": "parse_failed",
            "run_id": recorded.run_id,
            "finish_reason": recorded.finish_reason,
            "warnings": warnings,
            "parse_error": parse_error,
        }

    payload = TableUpdateV1Request(
        schema_version="table_update_v1",
        idempotency_key=idem,
        title=str(parsed.get("title") or f"Table Update (auto): {table_name}").strip() or "Table Update (auto)",
        summary_md=str(parsed.get("summary_md") or "").strip() or None,
        ops=list(parsed.get("ops") or []),
    )

    db2 = SessionLocal()
    try:
        proposed = propose_project_table_change_set(
            db=db2,
            request_id=req,
            actor_user_id=actor,
            project_id=pid,
            payload=payload,
        )
    except Exception as exc:
        return {
            "ok": False,
            "project_id": pid,
            "table_id": tid,
            "reason": "propose_failed",
            "run_id": recorded.run_id,
            "error_type": type(exc).__name__,
        }
    finally:
        db2.close()

    return {
        "ok": True,
        "project_id": pid,
        "table_id": tid,
        "chapter_id": chapter_id_effective,
        "run_id": recorded.run_id,
        "finish_reason": recorded.finish_reason,
        "warnings": warnings,
        **(proposed if isinstance(proposed, dict) else {"proposed": proposed}),
    }


def schedule_table_ai_update_task(
    *,
    db: Session | None = None,
    project_id: str,
    actor_user_id: str | None,
    request_id: str | None,
    table_id: str,
    chapter_id: str | None,
    chapter_token: str | None,
    focus: str | None,
    reason: str,
) -> str | None:
    """
    Fail-soft scheduler: ensure/enqueue a ProjectTask(kind=table_ai_update).
    """

    pid = str(project_id or "").strip()
    tid = str(table_id or "").strip()
    if not pid or not tid:
        return None

    token_norm = str(chapter_token or "").strip() or utc_now().isoformat().replace("+00:00", "Z")
    cid_norm = str(chapter_id or "").strip() or "none"
    table_prefix = tid[:12]
    chapter_prefix = cid_norm[:12]
    idempotency_key = f"table_ai:tbl:{table_prefix}:ch:{chapter_prefix}:since:{token_norm}:v1"

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
                kind=TABLE_AI_UPDATE_KIND,
                status="queued",
                idempotency_key=idempotency_key,
                params_json=_compact_json_dumps(
                    {
                        "reason": str(reason or "").strip() or "dirty",
                        "request_id": (str(request_id or "").strip() or None),
                        "table_id": tid,
                        "chapter_id": (str(chapter_id or "").strip() or None),
                        "chapter_token": token_norm,
                        "focus": (str(focus or "").strip() or None),
                        "change_set_idempotency_key": table_update_changeset_key_from_task_idempotency_key(idempotency_key),
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
