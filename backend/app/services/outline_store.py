from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.utils import new_id
from app.models.outline import Outline
from app.models.project import Project


def ensure_active_outline(db: Session, *, project: Project) -> Outline:
    if project.active_outline_id:
        row = db.get(Outline, project.active_outline_id)
        if row is not None:
            return row

    row = Outline(
        id=new_id(),
        project_id=project.id,
        title="默认大纲",
        content_md="",
        structure_json=None,
    )
    db.add(row)
    project.active_outline_id = row.id
    db.commit()
    db.refresh(row)
    return row
