from __future__ import annotations

import logging
from typing import Any, Literal

from app.core.errors import AppError
from app.core.logging import redact_secrets_text
from app.db.utils import new_id
from app.services.generation_service import PreparedLlmCall, with_param_overrides
from app.services.llm_retry import (
    LlmRetryExhausted,
    call_llm_and_record_with_retries,
    task_llm_max_attempts,
    task_llm_retry_base_seconds,
    task_llm_retry_jitter,
    task_llm_retry_max_seconds,
)
from app.services.output_parsers import extract_json_value, likely_truncated_json

logger = logging.getLogger("ainovel")

JsonRootType = Literal["object", "array", "any"]

_MAX_SCHEMA_CHARS = 6000
_MAX_RAW_OUTPUT_CHARS = 40000


def build_json_repair_prompt(*, schema: str, raw_output: str) -> tuple[str, str]:
    schema_text = str(schema or "").strip()[:_MAX_SCHEMA_CHARS]
    raw = str(raw_output or "").strip()[:_MAX_RAW_OUTPUT_CHARS]

    system = (
        "你是一个严格的 JSON 修复器。你的任务：把用户提供的模型原始输出修复为一个合法 JSON。"
        "只输出 JSON，不要解释，不要 Markdown，不要代码块。"
    )
    user = (
        "请把下面的内容修复为严格 JSON，并满足以下 schema：\n"
        f"{schema_text}\n\n"
        "要求：\n"
        "- 必须输出完整可解析的 JSON\n"
        "- 只输出 JSON，不能包含任何额外文本\n"
        "- 若缺字段请补默认值；若字段类型不匹配请修正\n\n"
        f"原始输出如下：\n{raw}"
    )
    return system, user


def _run_id_from_exc(exc: Exception) -> str | None:
    if isinstance(exc, AppError):
        details = exc.details if isinstance(getattr(exc, "details", None), dict) else {}
        run_id = str(details.get("run_id") or "").strip()
        if run_id:
            return run_id
    run_id = str(getattr(exc, "run_id", "") or "").strip()
    return run_id or None


def repair_json_once(
    *,
    request_id: str,
    actor_user_id: str,
    project_id: str,
    chapter_id: str | None,
    api_key: str,
    llm_call: PreparedLlmCall,
    raw_output: str,
    schema: str,
    expected_root: JsonRootType = "object",
    origin_run_id: str | None = None,
    origin_task: str | None = None,
) -> dict[str, Any]:
    """
    One-shot JSON repair helper (no retries).

    Returns:
    - ok=True: value/raw_json/repair_run_id
    - ok=False: reason + repair_run_id (if available) + parse_error / error_message
    """
    rid = str(request_id or "").strip() or f"json_repair:{new_id()}"
    actor = str(actor_user_id or "").strip()
    pid = str(project_id or "").strip()
    raw = str(raw_output or "")
    schema_text = str(schema or "")

    if not actor or not pid:
        return {"ok": False, "reason": "missing_context"}

    system, user = build_json_repair_prompt(schema=schema_text, raw_output=raw)

    try:
        llm_call2 = with_param_overrides(llm_call, {"temperature": 0, "max_tokens": 2048})
        max_attempts = task_llm_max_attempts(default=3)
        recorded, _attempts = call_llm_and_record_with_retries(
            logger=logger,
            request_id=rid,
            actor_user_id=actor,
            project_id=pid,
            chapter_id=str(chapter_id or "").strip() or None,
            run_type="json_repair",
            api_key=str(api_key or ""),
            prompt_system=system,
            prompt_user=user,
            llm_call=llm_call2,
            max_attempts=max_attempts,
            backoff_base_seconds=task_llm_retry_base_seconds(),
            backoff_max_seconds=task_llm_retry_max_seconds(),
            jitter=task_llm_retry_jitter(),
            run_params_extra_json={
                "task": "json_repair",
                "origin_task": (str(origin_task or "").strip() or None),
                "origin_run_id": (str(origin_run_id or "").strip() or None),
            },
        )
    except LlmRetryExhausted as exc:
        return {
            "ok": False,
            "reason": "llm_call_failed",
            "repair_run_id": exc.run_id,
            "error_type": exc.error_type,
            "error_message": exc.error_message[:400],
            "attempts": list(exc.attempts or []),
            "error": {
                "code": exc.error_code or "LLM_CALL_FAILED",
                "details": {"attempts": list(exc.attempts or [])},
            },
        }

    value, raw_json = extract_json_value(recorded.text)

    warnings: list[str] = []
    if recorded.finish_reason == "length":
        warnings.append("output_truncated")

    if expected_root == "object" and not isinstance(value, dict):
        parse_error: dict[str, Any] = {"code": "JSON_REPAIR_PARSE_ERROR", "message": "repair 输出不是 JSON object"}
        if likely_truncated_json(recorded.text):
            parse_error["hint"] = "输出疑似被截断（JSON 未闭合），可尝试增大 max_tokens 或减少修复目标"
        return {
            "ok": False,
            "reason": "parse_failed",
            "repair_run_id": recorded.run_id,
            "warnings": warnings,
            "parse_error": parse_error,
        }
    if expected_root == "array" and not isinstance(value, list):
        parse_error = {"code": "JSON_REPAIR_PARSE_ERROR", "message": "repair 输出不是 JSON array"}
        if likely_truncated_json(recorded.text):
            parse_error["hint"] = "输出疑似被截断（JSON 未闭合），可尝试增大 max_tokens 或减少修复目标"
        return {
            "ok": False,
            "reason": "parse_failed",
            "repair_run_id": recorded.run_id,
            "warnings": warnings,
            "parse_error": parse_error,
        }
    if expected_root == "any" and value is None:
        parse_error = {"code": "JSON_REPAIR_PARSE_ERROR", "message": "repair 输出无法解析为 JSON"}
        if likely_truncated_json(recorded.text):
            parse_error["hint"] = "输出疑似被截断（JSON 未闭合），可尝试增大 max_tokens 或减少修复目标"
        return {
            "ok": False,
            "reason": "parse_failed",
            "repair_run_id": recorded.run_id,
            "warnings": warnings,
            "parse_error": parse_error,
        }

    return {
        "ok": True,
        "repair_run_id": recorded.run_id,
        "finish_reason": recorded.finish_reason,
        "warnings": warnings,
        "value": value,
        "raw_json": raw_json,
    }
