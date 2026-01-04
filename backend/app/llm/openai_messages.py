from __future__ import annotations

from typing import Any

from app.llm.messages import ChatMessage, coalesce_system, flatten_messages, merge_consecutive, normalize_role


def openai_messages_from_list(*, messages: list[ChatMessage], merge_system_into_user: bool) -> list[dict[str, Any]]:
    normalized = merge_consecutive(messages)
    system, non_system = coalesce_system(normalized)
    if merge_system_into_user:
        merged_user = flatten_messages(non_system)
        merged = merged_user
        if system.strip():
            merged = f"{system}\n\n{merged_user}" if merged_user.strip() else system
        return [{"role": "user", "content": merged}]

    out: list[dict[str, Any]] = []
    if system.strip():
        out.append({"role": "system", "content": system})
    for msg in non_system:
        role = normalize_role(msg.role)
        payload: dict[str, Any] = {"role": role, "content": msg.content}
        if msg.name:
            payload["name"] = msg.name
        out.append(payload)
    if not out:
        out.append({"role": "user", "content": ""})
    return out

