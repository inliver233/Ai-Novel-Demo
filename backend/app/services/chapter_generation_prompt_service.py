from __future__ import annotations

from app.llm.messages import ChatMessage, coalesce_system, flatten_messages
from app.llm.redaction import redact_text
from app.schemas.chapter_generate import ChapterGenerateRequest
from app.services.mcp.service import McpResearchConfig as McpResearchConfigSvc
from app.services.mcp.service import McpToolCall as McpToolCallSvc

_MAX_MACRO_SEED_CHARS = 256


def resolve_macro_seed(*, request_id: str, body: object) -> str:
    seed = str(getattr(body, "macro_seed", "") or "").strip()
    if not seed:
        return request_id
    return seed[:_MAX_MACRO_SEED_CHARS]

def apply_prompt_override(
    *,
    prompt_system: str,
    prompt_user: str,
    prompt_messages: list[ChatMessage],
    body: ChapterGenerateRequest,
) -> tuple[str, str, list[ChatMessage], bool]:
    override = body.prompt_override
    if override is None:
        return prompt_system, prompt_user, prompt_messages, False

    override_messages: list[ChatMessage] = []
    for item in override.messages or []:
        role = str(item.role or "user").strip() or "user"
        content = str(item.content or "")
        name = str(item.name).strip() if isinstance(item.name, str) and item.name.strip() else None
        override_messages.append(ChatMessage(role=role, content=content, name=name))
    if override_messages:
        system, non_system = coalesce_system(override_messages)
        user = flatten_messages(non_system)
        return system, user, override_messages, True

    next_system = prompt_system if override.system is None else str(override.system or "")
    next_user = prompt_user if override.user is None else str(override.user or "")
    next_messages: list[ChatMessage] = []
    if next_system.strip():
        next_messages.append(ChatMessage(role="system", content=next_system))
    if next_user.strip():
        next_messages.append(ChatMessage(role="user", content=next_user))
    return next_system, next_user, next_messages, True

def _redact_prompt_override_for_params(body: ChapterGenerateRequest) -> dict[str, object] | None:
    override = body.prompt_override
    if override is None:
        return None
    data = override.model_dump()
    if isinstance(data.get("system"), str):
        data["system"] = redact_text(data["system"])
    if isinstance(data.get("user"), str):
        data["user"] = redact_text(data["user"])

    messages = data.get("messages")
    if isinstance(messages, list):
        for item in messages:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("content"), str):
                item["content"] = redact_text(item["content"])
    return data

def _redact_prompt_preview_for_params(
    *, prompt_system: str, prompt_user: str, prompt_messages: list[ChatMessage]
) -> dict[str, object]:
    return {
        "system": redact_text(prompt_system or ""),
        "user": redact_text(prompt_user or ""),
        "messages": [{"role": m.role, "content": redact_text(m.content or ""), "name": m.name} for m in prompt_messages],
    }

def build_prompt_inspector_params(
    *,
    macro_seed: str,
    prompt_overridden: bool,
    body: ChapterGenerateRequest,
    precheck_prompt_system: str,
    precheck_prompt_user: str,
    precheck_prompt_messages: list[ChatMessage],
    final_prompt_system: str,
    final_prompt_user: str,
    final_prompt_messages: list[ChatMessage],
) -> dict[str, object]:
    out: dict[str, object] = {
        "macro_seed": macro_seed,
        "prompt_overridden": bool(prompt_overridden),
        "precheck": _redact_prompt_preview_for_params(
            prompt_system=precheck_prompt_system,
            prompt_user=precheck_prompt_user,
            prompt_messages=precheck_prompt_messages,
        ),
        "final": _redact_prompt_preview_for_params(
            prompt_system=final_prompt_system,
            prompt_user=final_prompt_user,
            prompt_messages=final_prompt_messages,
        ),
    }
    override = _redact_prompt_override_for_params(body)
    if override is not None:
        out["override"] = override
    return out

def build_mcp_research_config(body: ChapterGenerateRequest) -> McpResearchConfigSvc:
    cfg = getattr(body, "mcp_research", None)
    if cfg is None:
        return McpResearchConfigSvc(enabled=False, allowlist=[], calls=[])

    calls: list[McpToolCallSvc] = []
    for item in getattr(cfg, "calls", None) or []:
        tool_name = str(getattr(item, "tool_name", "") or "").strip()
        if not tool_name:
            continue
        args = getattr(item, "args", None)
        calls.append(McpToolCallSvc(tool_name=tool_name, args=args if isinstance(args, dict) else {}))

    allowlist = list(getattr(cfg, "allowlist", None) or [])
    return McpResearchConfigSvc(
        enabled=bool(getattr(cfg, "enabled", False)),
        allowlist=[str(x).strip() for x in allowlist if isinstance(x, str) and str(x).strip()],
        calls=calls,
        timeout_seconds=getattr(cfg, "timeout_seconds", None),
        max_output_chars=getattr(cfg, "max_output_chars", None),
    )

def inject_mcp_research_into_values(*, values: dict[str, object], context_md: str) -> None:
    text = str(context_md or "").strip()
    if not text:
        return

    base_instruction = str(values.get("instruction") or "").rstrip()
    user_obj = values.get("user")
    if isinstance(user_obj, dict):
        base = str(user_obj.get("instruction") or "").rstrip()
        user_obj["instruction"] = (base + "\n\n【资料收集 - 参考资料】\n" + text).strip()
    values["instruction"] = (base_instruction + "\n\n【资料收集 - 参考资料】\n" + text).strip()
    values["mcp_research"] = text

def build_mcp_research_params(
    *, cfg: McpResearchConfigSvc, applied: bool, tool_run_ids: list[str], warnings: list[str]
) -> dict[str, object]:
    return {
        "enabled": bool(cfg.enabled),
        "applied": bool(applied),
        "allowlist": list(cfg.allowlist or []),
        "tool_run_ids": list(tool_run_ids),
        "warnings": list(warnings or []),
    }

