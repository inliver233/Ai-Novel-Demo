from __future__ import annotations

from typing import Any, Literal

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.project_default_style import ProjectDefaultStyle
from app.models.writing_style import WritingStyle


StyleResolutionSource = Literal["request", "project_default", "settings_fallback", "none", "disabled"]


def resolve_style_guide(
    db: Session,
    *,
    project_id: str,
    user_id: str,
    requested_style_id: str | None,
    include_style_guide: bool,
    settings_style_guide: str,
) -> tuple[str, dict[str, Any]]:
    """
    Resolve the effective style_guide text for prompt rendering.

    Priority: request(style_id) > project_default(style_id) > settings_style_guide fallback.
    """
    if not include_style_guide:
        return "", {"style_id": None, "source": "disabled"}

    settings_style_guide = (settings_style_guide or "").strip()

    def _can_use_style(style: WritingStyle) -> bool:
        return bool(style.is_preset) or (style.owner_user_id == user_id)

    if requested_style_id is not None:
        style = db.get(WritingStyle, requested_style_id)
        if style is None:
            raise AppError.validation(message="style_id 不存在")
        if not _can_use_style(style):
            raise AppError.forbidden(message="无权限使用该风格")
        return (style.prompt_content or "").strip(), {"style_id": style.id, "source": "request"}

    default = db.get(ProjectDefaultStyle, project_id)
    if default is not None and default.style_id:
        style = db.get(WritingStyle, default.style_id)
        if style is not None and _can_use_style(style):
            return (style.prompt_content or "").strip(), {"style_id": style.id, "source": "project_default"}

    if settings_style_guide:
        return settings_style_guide, {"style_id": None, "source": "settings_fallback"}

    return "", {"style_id": None, "source": "none"}

