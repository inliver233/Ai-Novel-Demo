from __future__ import annotations

from dataclasses import dataclass


_VALID_ROLES: set[str] = {"system", "user", "assistant", "tool"}


def normalize_role(role: str) -> str:
    value = (role or "").strip().lower()
    if value == "model":
        return "assistant"
    if value in _VALID_ROLES:
        return value
    return "user"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    content: str
    name: str | None = None


def merge_consecutive(messages: list[ChatMessage]) -> list[ChatMessage]:
    merged: list[ChatMessage] = []
    for msg in messages:
        content = str(msg.content or "")
        if not content.strip():
            continue
        role = normalize_role(msg.role)
        name = msg.name
        if merged and merged[-1].role == role and merged[-1].name == name:
            prev = merged[-1]
            merged[-1] = ChatMessage(role=role, content=f"{prev.content}\n\n{content}", name=name)
        else:
            merged.append(ChatMessage(role=role, content=content, name=name))
    return merged


def coalesce_system(messages: list[ChatMessage]) -> tuple[str, list[ChatMessage]]:
    system_parts: list[str] = []
    non_system: list[ChatMessage] = []
    for msg in messages:
        role = normalize_role(msg.role)
        if role == "system":
            if str(msg.content or "").strip():
                system_parts.append(str(msg.content))
            continue
        non_system.append(ChatMessage(role=role, content=str(msg.content or ""), name=msg.name))
    return "\n\n".join([p for p in system_parts if p.strip()]), non_system


def flatten_messages(messages: list[ChatMessage]) -> str:
    parts: list[str] = []
    for msg in messages:
        role = normalize_role(msg.role)
        content = str(msg.content or "")
        if not content.strip():
            continue
        if role == "user":
            parts.append(content)
        else:
            parts.append(f"[{role.upper()}]\n{content}")
    return "\n\n".join(parts)

