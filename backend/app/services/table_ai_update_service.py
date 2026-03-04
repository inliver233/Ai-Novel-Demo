from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.logging import exception_log_fields, log_event, redact_secrets_text
from app.db.session import SessionLocal
from app.db.utils import new_id, utc_now
from app.models.chapter import Chapter
from app.models.generation_run import GenerationRun
from app.models.llm_preset import LLMPreset
from app.models.project import Project
from app.models.project_table import ProjectTable, ProjectTableRow
from app.models.project_task import ProjectTask
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
from app.services.memory_update_service import propose_project_table_change_set
from app.services.output_parsers import extract_json_value, likely_truncated_json
from app.services.table_executor import MAX_OPS_V1, TableRowOpV1, TableUpdateV1Request, is_key_value_schema

logger = logging.getLogger("ainovel")


TABLE_AI_UPDATE_KIND = "table_ai_update"

_MAX_ROWS_IN_PROMPT = 80
_MAX_CHAPTER_CHARS = 16000
_MAX_TOKENS_PRIMARY_V1 = 1024
_MAX_TOKENS_RETRY_V1 = 512
_MAX_OPS_AI_V1 = 25
_MAX_OPS_AI_RETRY_V1 = 12


def _compact_json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _resolve_table_llm_call(
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
            task_key=TABLE_AI_UPDATE_KIND,
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


def _find_latest_run_id_for_request(*, project_id: str, request_id: str, run_type: str) -> str | None:
    """
    Best-effort: resolve the run_id written by call_llm_and_record when it raises.
    """
    pid = str(project_id or "").strip()
    rid = str(request_id or "").strip()
    rtype = str(run_type or "").strip()
    if not pid or not rid or not rtype:
        return None

    db = SessionLocal()
    try:
        q = (
            select(GenerationRun.id)
            .where(
                GenerationRun.project_id == pid,
                GenerationRun.request_id == rid,
                GenerationRun.type == rtype,
            )
            .order_by(GenerationRun.created_at.desc(), GenerationRun.id.desc())
            .limit(1)
        )
        return db.execute(q).scalars().first()
    except Exception:
        return None
    finally:
        db.close()


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
    cols = schema.get("columns") if isinstance(schema.get("columns"), list) else []
    col_by_key = {
        str(c.get("key") or "").strip(): c
        for c in cols
        if isinstance(c, dict) and str(c.get("key") or "").strip()
    }
    value_type = str((col_by_key.get("value") or {}).get("type") or "").strip().lower()
    focus_text = (focus or "").strip()

    chapter_number = int(getattr(chapter, "number", 0) or 0) if chapter is not None else 0
    chapter_title = str(getattr(chapter, "title", "") or "") if chapter is not None else ""
    chapter_plan = str(getattr(chapter, "plan", "") or "") if chapter is not None else ""
    chapter_content = _truncate(getattr(chapter, "content_md", "") if chapter is not None else "", limit=_MAX_CHAPTER_CHARS)

    system = (
        "你是数据同步助手：负责把最新章节内容中的“可用数字表示的状态变化”同步到「结构化记忆（数值表格）」中。\n"
        "重要边界：不要把剧情、人物关系、设定文本写进表格；这些属于世界书/图谱/剧情记忆。\n"
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
        f"- ops 必须是数组（允许为空数组，当无需更新时），且长度 <= {_MAX_OPS_AI_V1}（输出尽量短，避免超时；不要重复输出未变化的行）\n"
        "- 只能修改给定的 table_id（不要写其它 table_id）\n"
        '- op=upsert 时 data 必填；op=delete 时 row_id 必填且 data 必须为 null\n'
        "- data 必须严格符合 schema.columns（字段名与类型）\n"
        "- number 字段必须输出 JSON number（不要用字符串，例如 10 而不是 \"10\"）\n"
        "- 信息不足时宁可少更新：不要猜测、不要捏造、不要凭空新增 key\n"
        "- 若章节只描述增量（+/-），可基于 existing_rows 中的现值计算新值；若现值缺失则保守不更新\n"
    )

    if is_kv:
        system += (
            "\n"
            "本表为 Key/Value 结构（columns: key,value）。\n"
            "- 你可以省略 upsert 的 row_id：后端会用 data.key 匹配现有行并更新，避免重复 key。\n"
            "- 严禁创建重复 key：同一个 key 只能对应一行。\n"
        )
        if value_type:
            system += f"- value 字段类型为 {value_type}（必须严格匹配 schema；number 不要加引号）。\n"

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
    if ops_raw is None:
        warnings.append("ops_missing")
        ops_raw = []
    if not isinstance(ops_raw, list):
        data: dict[str, Any] = {"title": title_out, "summary_md": summary_out, "ops": [], "raw_output": text}
        if raw_json:
            data["raw_json"] = raw_json
        return data, warnings, {"code": "TABLE_UPDATE_PARSE_ERROR", "message": "ops 必须是数组"}
    if not ops_raw:
        warnings.append("ops_empty")
        data = {"title": title_out, "summary_md": summary_out, "ops": [], "raw_output": text}
        if raw_json:
            data["raw_json"] = raw_json
        if finish_reason == "length":
            warnings.append("output_truncated")
        return data, warnings, None

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

        resolved = _resolve_table_llm_call(db=db, project=project, actor_user_id=actor)
        if resolved is None:
            return {"ok": False, "project_id": pid, "reason": "llm_preset_missing"}

        llm_call, resolved_api_key = resolved
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
            + "【重试模式】上一轮调用失败/超时。请输出更短、更保守的更新：\n"
            + "- 只输出裸 JSON（不要 Markdown，不要代码块）\n"
            + f"- ops 长度 <= {_MAX_OPS_AI_RETRY_V1}\n"
            + "- 只更新最确定的 1~3 个 key/行；不要穷举；不要重复输出未变化的行\n"
        )

        max_attempts = task_llm_max_attempts(default=3)
        recorded, llm_attempts = call_llm_and_record_with_retries(
            logger=logger,
            request_id=req,
            actor_user_id=actor,
            project_id=pid,
            chapter_id=chapter_id_effective,
            run_type="table_ai_update_auto_propose",
            api_key=str(resolved_api_key),
            prompt_system=prompt_system,
            prompt_user=prompt_user,
            llm_call=llm_call,
            run_params_extra_json={
                "task": TABLE_AI_UPDATE_KIND,
                "schema_version": "table_update_v1",
                "table_id": tid,
                "table_name": table_name,
                "kv_mode": bool(is_key_value_schema(schema_dict)),
                "rows_in_prompt": int(len(existing_rows)),
            },
            max_attempts=max_attempts,
            retry_prompt_system=retry_system,
            llm_call_overrides_by_attempt={
                1: {"temperature": 0.2, "max_tokens": _clamp_max_tokens(_MAX_TOKENS_PRIMARY_V1)},
                2: {"temperature": 0.1, "max_tokens": _clamp_max_tokens(_MAX_TOKENS_RETRY_V1)},
                3: {"temperature": 0.0, "max_tokens": _clamp_max_tokens(_MAX_TOKENS_RETRY_V1)},
            },
            backoff_base_seconds=task_llm_retry_base_seconds(),
            backoff_max_seconds=task_llm_retry_max_seconds(),
            jitter=task_llm_retry_jitter(),
        )
    except LlmRetryExhausted as exc:
        run_id = str(exc.run_id or "").strip() or None
        if not run_id:
            for attempt in reversed(list(exc.attempts or [])):
                rid2 = str(attempt.get("request_id") or "").strip()
                if not rid2:
                    continue
                found = _find_latest_run_id_for_request(
                    project_id=pid,
                    request_id=rid2,
                    run_type="table_ai_update_auto_propose",
                )
                if found:
                    run_id = found
                    break

        log_event(
            logger,
            "warning",
            event="TABLE_AI_UPDATE_LLM_ERROR",
            project_id=pid,
            table_id=tid,
            run_id=run_id,
            error_type=str(exc.error_type),
            request_id=req,
            **exception_log_fields(exc.last_exception),
        )
        return {
            "ok": False,
            "project_id": pid,
            "table_id": tid,
            "reason": "llm_call_failed",
            "run_id": run_id,
            "error_type": exc.error_type,
            "error_message": exc.error_message[:400],
            "attempts": list(exc.attempts or []),
            "error": {
                "code": exc.error_code or "LLM_CALL_FAILED",
                "details": {"attempts": list(exc.attempts or [])},
            },
        }

    repair_run_id: str | None = None
    parsed, warnings, parse_error = parse_table_update_output_v1(
        recorded.text, expected_table_id=tid, finish_reason=recorded.finish_reason
    )
    if len(list(llm_attempts or [])) >= 2:
        warnings = [*list(warnings or []), "llm_retry_used"]
    if parse_error is not None:
        repair_schema = (
            "{\n"
            '  "title": string | null,\n'
            '  "summary_md": string | null,\n'
            '  "ops": [\n'
            "    {\n"
            '      "op": "upsert" | "delete",\n'
            '      "table_id": string,\n'
            '      "row_id": string | null,\n'
            '      "row_index": int | null,\n'
            '      "data": object | null\n'
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
            chapter_id=chapter_id_effective,
            api_key=str(resolved_api_key),
            llm_call=llm_call,
            raw_output=recorded.text,
            schema=repair_schema,
            expected_root="object",
            origin_run_id=recorded.run_id,
            origin_task=TABLE_AI_UPDATE_KIND,
        )
        repair_run_id = str(repair.get("repair_run_id") or "").strip() or None
        warnings2 = [*list(warnings or []), *list(repair.get("warnings") or [])]

        if bool(repair.get("ok")):
            repaired_text = str(repair.get("raw_json") or "").strip()
            parsed2, warnings3, parse_error2 = parse_table_update_output_v1(
                repaired_text,
                expected_table_id=tid,
                finish_reason=str(repair.get("finish_reason") or "").strip() or None,
            )
            warnings2.extend(list(warnings3 or []))
            if parse_error2 is None:
                parsed = parsed2
                warnings = warnings2
                parse_error = None
            else:
                payload = parse_error2 if isinstance(parse_error2, dict) else {"message": str(parse_error2 or "")}
                if isinstance(payload, dict):
                    payload = dict(payload)
                    payload["original_parse_error"] = parse_error
                    if repair_run_id:
                        payload["repair_run_id"] = repair_run_id
                return {
                    "ok": False,
                    "project_id": pid,
                    "table_id": tid,
                    "reason": "parse_failed",
                    "run_id": recorded.run_id,
                    "repair_run_id": repair_run_id,
                    "finish_reason": recorded.finish_reason,
                    "warnings": warnings2,
                    "parse_error": payload,
                }
        else:
            payload = parse_error if isinstance(parse_error, dict) else {"message": str(parse_error or "")}
            if isinstance(payload, dict):
                payload = dict(payload)
                if repair_run_id:
                    payload["repair_run_id"] = repair_run_id
                if repair.get("reason"):
                    payload["repair_reason"] = repair.get("reason")
                if repair.get("parse_error"):
                    payload["repair_parse_error"] = repair.get("parse_error")
                if repair.get("error_message"):
                    payload["repair_error_message"] = repair.get("error_message")
            return {
                "ok": False,
                "project_id": pid,
                "table_id": tid,
                "reason": "parse_failed",
                "run_id": recorded.run_id,
                "repair_run_id": repair_run_id,
                "finish_reason": recorded.finish_reason,
                "warnings": warnings2,
                "parse_error": payload,
            }

        if parse_error is not None:
            payload = dict(parse_error) if isinstance(parse_error, dict) else {"message": str(parse_error or "")}
            if repair_run_id:
                payload["repair_run_id"] = repair_run_id
            return {
                "ok": False,
                "project_id": pid,
                "table_id": tid,
                "reason": "parse_failed",
                "run_id": recorded.run_id,
                "repair_run_id": repair_run_id,
                "finish_reason": recorded.finish_reason,
                "warnings": warnings2,
                "parse_error": payload,
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
        if isinstance(exc, AppError):
            return {
                "ok": False,
                "project_id": pid,
                "table_id": tid,
                "reason": "propose_failed",
                "run_id": recorded.run_id,
                "repair_run_id": repair_run_id,
                "error": {"code": exc.code, "message": exc.message, "details": exc.details},
            }
        return {
            "ok": False,
            "project_id": pid,
            "table_id": tid,
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
        "table_id": tid,
        "chapter_id": chapter_id_effective,
        "run_id": recorded.run_id,
        "repair_run_id": repair_run_id,
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
