from __future__ import annotations

from app.models.character import Character


def format_characters(chars: list[Character]) -> str:
    if not chars:
        return ""
    lines: list[str] = []
    for c in chars:
        role = f"（{c.role}）" if c.role else ""
        lines.append(f"- {c.name}{role}")
        if c.profile:
            snippet = c.profile.strip()
            if snippet:
                lines.append(f"  - 档案：{snippet}")
        if c.notes:
            snippet = c.notes.strip()
            if snippet:
                lines.append(f"  - 备注：{snippet}")
    return "\n".join(lines)
