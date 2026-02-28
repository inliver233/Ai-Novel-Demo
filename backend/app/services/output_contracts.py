from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import ValidationError

from app.services.output_parsers import (
    extract_json_value,
    build_outline_fix_json_prompt,
    likely_truncated_json,
    parse_chapter_analysis_output,
    parse_chapter_output,
    parse_outline_output,
    parse_tag_output,
)
from app.schemas.memory_update import MemoryUpdateOpV1
from app.schemas.worldbook_auto_update import WorldbookAutoUpdateOpV1


OutputContractType = Literal["markers", "json", "tags", "analysis_json", "memory_update_json", "worldbook_auto_update_json"]


def _normalize_memory_update_op_v1(item: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """
    Compatibility normalizer for real-world LLM drift.

    Supports shapes like:
    - entities.after.entity_id -> op.target_id
    - entities.after.type -> entities.after.entity_type
    - relations.after.relation_id -> op.target_id
    - relations.after.from_id/to_id -> from_entity_id/to_entity_id
    - relations.after.evidence_ids -> op.evidence_ids
    - evidence.after.target_id -> op.target_id
    """
    warnings: list[str] = []
    obj = dict(item)
    after = obj.get("after")
    if not isinstance(after, dict):
        return obj, warnings

    after2 = dict(after)

    # Some outputs nest evidence_ids inside after.
    after_evidence_ids = after2.get("evidence_ids")
    if isinstance(after_evidence_ids, list):
        existing = obj.get("evidence_ids")
        if isinstance(existing, list):
            obj["evidence_ids"] = [*existing, *after_evidence_ids]
        elif existing is None:
            obj["evidence_ids"] = after_evidence_ids
        warnings.append("memory_update:normalized_evidence_ids_from_after")
    after2.pop("evidence_ids", None)

    # Some outputs nest target_id inside after (e.g., evidence.after.target_id).
    if not (obj.get("target_id") or "").strip() and isinstance(after2.get("target_id"), str) and str(after2.get("target_id") or "").strip():
        obj["target_id"] = str(after2.get("target_id") or "").strip()
        warnings.append("memory_update:normalized_after.target_id_to_op.target_id")

    # Drift: entities.after.entity_id (preferred to op.target_id)
    if not (obj.get("target_id") or "").strip() and isinstance(after2.get("entity_id"), str) and str(after2.get("entity_id") or "").strip():
        obj["target_id"] = str(after2.get("entity_id") or "").strip()
        warnings.append("memory_update:normalized_after.entity_id_to_op.target_id")

    # Drift: relations.after.relation_id (preferred to op.target_id)
    if not (obj.get("target_id") or "").strip() and isinstance(after2.get("relation_id"), str) and str(after2.get("relation_id") or "").strip():
        obj["target_id"] = str(after2.get("relation_id") or "").strip()
        warnings.append("memory_update:normalized_after.relation_id_to_op.target_id")

    # Drift: entities.after.type -> entities.after.entity_type
    if isinstance(after2.get("type"), str) and str(after2.get("type") or "").strip() and not str(after2.get("entity_type") or "").strip():
        after2["entity_type"] = str(after2.get("type") or "").strip()
        warnings.append("memory_update:normalized_after.type_to_entity_type")

    # Drift: relations.after.from_id/to_id -> from_entity_id/to_entity_id
    if isinstance(after2.get("from_id"), str) and str(after2.get("from_id") or "").strip() and not str(after2.get("from_entity_id") or "").strip():
        after2["from_entity_id"] = str(after2.get("from_id") or "").strip()
        warnings.append("memory_update:normalized_after.from_id_to_from_entity_id")
    if isinstance(after2.get("to_id"), str) and str(after2.get("to_id") or "").strip() and not str(after2.get("to_entity_id") or "").strip():
        after2["to_entity_id"] = str(after2.get("to_id") or "").strip()
        warnings.append("memory_update:normalized_after.to_id_to_to_entity_id")

    # Drop drift-only fields from after to satisfy strict schema.
    for k in ("target_id", "entity_id", "relation_id", "from_id", "to_id", "type"):
        after2.pop(k, None)

    obj["after"] = after2
    return obj, warnings


@dataclass(frozen=True, slots=True)
class OutputParseResult:
    data: dict[str, Any]
    warnings: list[str]
    parse_error: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class OutputContract:
    type: OutputContractType
    tag: str | None = None
    output_key: str | None = None

    @staticmethod
    def _safe_pydantic_errors(exc: Exception) -> list[dict[str, Any]] | None:
        if not isinstance(exc, ValidationError):
            return None
        out: list[dict[str, Any]] = []
        for e in exc.errors(include_url=False):
            if not isinstance(e, dict):
                continue
            e2: dict[str, Any] = {k: e.get(k) for k in ("loc", "msg", "type", "ctx") if k in e}
            ctx = e2.get("ctx")
            if isinstance(ctx, dict):
                ctx2: dict[str, Any] = {}
                for ck, cv in ctx.items():
                    if isinstance(cv, str) and len(cv) > 200:
                        ctx2[ck] = cv[:200]
                    else:
                        ctx2[ck] = cv
                e2["ctx"] = ctx2
            out.append(e2)
        return out

    def parse(self, text: str, *, finish_reason: str | None = None) -> OutputParseResult:
        if self.type == "markers":
            data, warnings, parse_error = parse_chapter_output(text, finish_reason=finish_reason)
            return OutputParseResult(data=data, warnings=warnings, parse_error=parse_error)

        if self.type == "json":
            data, warnings, parse_error = parse_outline_output(text)
            if finish_reason == "length":
                warnings = list(warnings)
                warnings.append("output_truncated")
                if parse_error is not None:
                    parse_error = dict(parse_error)
                    parse_error.setdefault(
                        "hint",
                        "输出疑似被截断（finish_reason=length），可尝试增大 max_tokens 或降低目标字数/章节数",
                    )
            return OutputParseResult(data=data, warnings=warnings, parse_error=parse_error)

        if self.type == "analysis_json":
            data, warnings, parse_error = parse_chapter_analysis_output(text)
            if finish_reason == "length":
                warnings = list(warnings)
                warnings.append("output_truncated")
                if parse_error is not None:
                    parse_error = dict(parse_error)
                    parse_error.setdefault(
                        "hint",
                        "输出疑似被截断（finish_reason=length），可尝试增大 max_tokens 或减少分析输出长度",
                    )
            return OutputParseResult(data=data, warnings=warnings, parse_error=parse_error)

        if self.type == "memory_update_json":
            warnings: list[str] = []
            value, raw_json = extract_json_value(text)
            if isinstance(value, list):
                value = {"ops": value}
            if not isinstance(value, dict):
                parse_error: dict[str, Any] = {"code": "MEMORY_UPDATE_PARSE_ERROR", "message": "无法从模型输出解析 memory_update JSON"}
                if likely_truncated_json(text):
                    parse_error["hint"] = "输出疑似被截断（JSON 未闭合），可尝试增大 max_tokens 或减少输出长度"
                data = {"title": "", "summary_md": "", "ops": [], "raw_output": text}
                return OutputParseResult(data=data, warnings=warnings, parse_error=parse_error)

            title = value.get("title")
            title_out = title.strip() if isinstance(title, str) else ""
            summary_md = value.get("summary_md")
            summary_out = summary_md.strip() if isinstance(summary_md, str) else ""

            ops_raw = value.get("ops")
            if ops_raw is None:
                warnings.append("ops_missing")
                ops_raw = []
            if not isinstance(ops_raw, list):
                data = {"title": title_out, "summary_md": summary_out, "ops": [], "raw_output": text}
                if raw_json:
                    data["raw_json"] = raw_json
                return OutputParseResult(
                    data=data,
                    warnings=warnings,
                    parse_error={"code": "MEMORY_UPDATE_PARSE_ERROR", "message": "ops 必须是数组"},
                )
            if not ops_raw:
                warnings.append("ops_empty")
                data = {"title": title_out, "summary_md": summary_out, "ops": [], "raw_output": text}
                if raw_json:
                    data["raw_json"] = raw_json
                if finish_reason == "length":
                    warnings.append("output_truncated")
                return OutputParseResult(data=data, warnings=warnings, parse_error=None)

            ops_out: list[dict[str, Any]] = []
            for idx, item in enumerate(ops_raw):
                if not isinstance(item, dict):
                    return OutputParseResult(
                        data={"title": title_out, "summary_md": summary_out, "ops": [], "raw_output": text},
                        warnings=warnings,
                        parse_error={"code": "MEMORY_UPDATE_PARSE_ERROR", "message": f"ops[{idx}] 必须是 object", "idx": idx},
                    )
                try:
                    normalized, w = _normalize_memory_update_op_v1(item)
                    warnings.extend(w)
                    op = MemoryUpdateOpV1.model_validate(normalized)
                except Exception as exc:
                    pydantic_errors = self._safe_pydantic_errors(exc)
                    parse_error: dict[str, Any] = {
                        "code": "MEMORY_UPDATE_PARSE_ERROR",
                        "message": f"ops[{idx}] schema invalid:{type(exc).__name__}",
                        "idx": idx,
                    }
                    if pydantic_errors is not None:
                        parse_error["errors"] = pydantic_errors
                    return OutputParseResult(
                        data={"title": title_out, "summary_md": summary_out, "ops": [], "raw_output": text},
                        warnings=warnings,
                        parse_error=parse_error,
                    )
                ops_out.append(dict(op.model_dump()))

            data: dict[str, Any] = {"title": title_out, "summary_md": summary_out, "ops": ops_out, "raw_output": text}
            if raw_json:
                data["raw_json"] = raw_json
            if finish_reason == "length":
                warnings.append("output_truncated")
            return OutputParseResult(data=data, warnings=warnings, parse_error=None)

        if self.type == "worldbook_auto_update_json":
            warnings: list[str] = []
            value, raw_json = extract_json_value(text)
            if isinstance(value, list):
                value = {"ops": value}
            if not isinstance(value, dict):
                parse_error: dict[str, Any] = {
                    "code": "WORLDBOOK_AUTO_UPDATE_PARSE_ERROR",
                    "message": "无法从模型输出解析 worldbook_auto_update JSON",
                }
                if likely_truncated_json(text):
                    parse_error["hint"] = "输出疑似被截断（JSON 未闭合），可尝试增大 max_tokens 或减少输出长度"
                data = {"title": "", "summary_md": "", "ops": [], "raw_output": text}
                return OutputParseResult(data=data, warnings=warnings, parse_error=parse_error)

            schema_version = value.get("schema_version")
            schema_version_norm = schema_version.strip() if isinstance(schema_version, str) else ""
            if not schema_version_norm:
                warnings.append("schema_version_missing")
            elif schema_version_norm != "worldbook_auto_update_v1":
                warnings.append("schema_version_invalid")

            title = value.get("title")
            title_out = title.strip() if isinstance(title, str) else ""
            summary_md = value.get("summary_md")
            summary_out = summary_md.strip() if isinstance(summary_md, str) else ""

            ops_raw = value.get("ops")
            if ops_raw is None:
                warnings.append("ops_missing")
                ops_raw = []
            if not isinstance(ops_raw, list):
                data = {"title": title_out, "summary_md": summary_out, "ops": [], "raw_output": text}
                if raw_json:
                    data["raw_json"] = raw_json
                return OutputParseResult(
                    data=data,
                    warnings=warnings,
                    parse_error={"code": "WORLDBOOK_AUTO_UPDATE_PARSE_ERROR", "message": "ops 必须是数组"},
                )
            if not ops_raw:
                warnings.append("ops_empty")
                data = {"title": title_out, "summary_md": summary_out, "ops": [], "raw_output": text}
                if raw_json:
                    data["raw_json"] = raw_json
                if finish_reason == "length":
                    warnings.append("output_truncated")
                return OutputParseResult(data=data, warnings=warnings, parse_error=None)

            ops_out: list[dict[str, Any]] = []
            for idx, item in enumerate(ops_raw):
                if not isinstance(item, dict):
                    return OutputParseResult(
                        data={"title": title_out, "summary_md": summary_out, "ops": [], "raw_output": text},
                        warnings=warnings,
                        parse_error={
                            "code": "WORLDBOOK_AUTO_UPDATE_PARSE_ERROR",
                            "message": f"ops[{idx}] 必须是 object",
                            "idx": idx,
                        },
                    )
                try:
                    op = WorldbookAutoUpdateOpV1.model_validate(item)
                except Exception as exc:
                    pydantic_errors = self._safe_pydantic_errors(exc)
                    parse_error: dict[str, Any] = {
                        "code": "WORLDBOOK_AUTO_UPDATE_PARSE_ERROR",
                        "message": f"ops[{idx}] schema invalid:{type(exc).__name__}",
                        "idx": idx,
                    }
                    if pydantic_errors is not None:
                        parse_error["errors"] = pydantic_errors
                    return OutputParseResult(
                        data={"title": title_out, "summary_md": summary_out, "ops": [], "raw_output": text},
                        warnings=warnings,
                        parse_error=parse_error,
                    )
                ops_out.append(dict(op.model_dump()))

            data: dict[str, Any] = {"title": title_out, "summary_md": summary_out, "ops": ops_out, "raw_output": text}
            if raw_json:
                data["raw_json"] = raw_json
            if finish_reason == "length":
                warnings.append("output_truncated")
            return OutputParseResult(data=data, warnings=warnings, parse_error=None)

        if self.type == "tags":
            tag = (self.tag or "").strip()
            if not tag:
                return OutputParseResult(
                    data={self.output_key or "value": "", "raw_output": text},
                    warnings=[],
                    parse_error={"code": "TAG_PARSE_ERROR", "message": "未配置 tag"},
                )
            data, warnings, parse_error = parse_tag_output(text, tag=tag, output_key=self.output_key)
            return OutputParseResult(data=data, warnings=warnings, parse_error=parse_error)

        return OutputParseResult(
            data={"raw_output": text},
            warnings=[],
            parse_error={"code": "OUTPUT_CONTRACT_ERROR", "message": "不支持的 OutputContract"},
        )


def contract_for_task(task: str) -> OutputContract:
    task = (task or "").strip()
    if task == "outline_generate":
        return OutputContract(type="json")
    if task == "chapter_analyze":
        return OutputContract(type="analysis_json")
    if task == "chapter_generate":
        return OutputContract(type="markers")
    if task == "memory_update":
        return OutputContract(type="memory_update_json")
    if task == "plan_chapter":
        return OutputContract(type="tags", tag="plan", output_key="plan")
    if task == "post_edit":
        return OutputContract(type="tags", tag="rewrite", output_key="content_md")
    if task == "content_optimize":
        return OutputContract(type="tags", tag="content", output_key="content_md")
    if task == "chapter_rewrite":
        return OutputContract(type="tags", tag="rewrite", output_key="content_md")
    if task == "worldbook_auto_update":
        return OutputContract(type="worldbook_auto_update_json")
    return OutputContract(type="markers")


def build_repair_prompt_for_task(task: str, *, raw_output: str) -> tuple[str, str, str] | None:
    """
    Returns (system, user, run_type) if the task supports repair prompts.
    """
    task = (task or "").strip()
    if task == "outline_generate":
        system, user = build_outline_fix_json_prompt(raw_output)
        return system, user, "outline_fix_json"
    return None
