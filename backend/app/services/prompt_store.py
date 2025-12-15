from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.utils import new_id
from app.models.character import Character
from app.models.prompt_template import PromptTemplate
from app.services.defaults import default_prompt_templates


def ensure_prompt_templates(db: Session, project_id: str) -> dict[str, PromptTemplate]:
    """Ensure default prompt templates exist for the project.

    Note: this function commits when it creates missing templates.
    """
    existing: dict[str, PromptTemplate] = {
        r.type: r for r in db.execute(select(PromptTemplate).where(PromptTemplate.project_id == project_id)).scalars().all()
    }
    created = False
    for t in default_prompt_templates():
        if t.type in existing:
            continue
        row = PromptTemplate(
            id=new_id(),
            project_id=project_id,
            type=t.type,
            system_template=t.system_template,
            user_template=t.user_template,
        )
        db.add(row)
        existing[t.type] = row
        created = True
    if created:
        db.commit()
    return existing


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
