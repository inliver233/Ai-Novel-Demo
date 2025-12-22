from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.services.output_parsers import build_outline_fix_json_prompt, parse_chapter_output, parse_outline_output, parse_tag_output


OutputContractType = Literal["markers", "json", "tags"]


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
    if task == "chapter_generate":
        return OutputContract(type="markers")
    if task == "plan_chapter":
        return OutputContract(type="tags", tag="plan", output_key="plan")
    if task == "post_edit":
        return OutputContract(type="tags", tag="rewrite", output_key="content_md")
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
