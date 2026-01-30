from __future__ import annotations

import json
from typing import Any

from app.schemas.worldbook_auto_update import WorldbookAutoUpdateSchemaVersion


WORLDBOOK_AUTO_UPDATE_TASK = "worldbook_auto_update"
WORLDBOOK_AUTO_UPDATE_SCHEMA_VERSION: WorldbookAutoUpdateSchemaVersion = "worldbook_auto_update_v1"


def build_worldbook_auto_update_prompt_v1(
    *,
    project_id: str,
    chapter_content_md: str,
    outline_md: str | None,
    existing_worldbook_titles: list[str],
) -> tuple[str, str]:
    """
    Prompt contract (v1):

    The model must output a single JSON object with:
    - schema_version: "worldbook_auto_update_v1"
    - title?: string
    - summary_md?: string
    - ops: list of operations (create/update/merge/dedupe)

    Ops strategy (high-level):
    - create: new entry when concept does not exist.
    - update: patch an existing entry matched by title/alias.
    - merge: merge missing details into an existing entry (avoid overwriting good existing content).
    - dedupe: propose canonical_title + duplicates list to merge/delete.
    """

    pid = str(project_id or "").strip()
    outline_text = (outline_md or "").strip()
    chapter_text = (chapter_content_md or "").strip()

    existing_titles = [str(t or "").strip() for t in (existing_worldbook_titles or []) if str(t or "").strip()]

    system = (
        "你是小说写作助手，负责把最新章节/大纲中的关键设定抽取为「世界书条目」自动更新提议。\n"
        "你必须只输出一个 JSON（允许使用 ```json 代码块包裹）。不要输出任何其它文字。\n"
        f"schema_version 必须是 {json.dumps(WORLDBOOK_AUTO_UPDATE_SCHEMA_VERSION, ensure_ascii=False)}。\n"
        "ops 是一个数组，每个 op 必须是以下之一：create / update / merge / dedupe。\n"
        "严格遵守：\n"
        "- 不要捏造不存在的设定；信息不足则宁可少写。\n"
        "- 避免重复条目：优先 update/merge，只有不存在才 create。\n"
        "- merge 时倾向补全缺失信息（append_missing），不要覆盖已有内容。\n"
        "- dedupe 用于指出重复条目并给出 canonical_title 与 duplicate_titles。\n"
        "- keywords/aliases 用于提高触发命中（别名/同义词/外号）。\n"
    )

    user = (
        f"project_id: {pid}\n\n"
        "=== existing_worldbook_titles ===\n"
        f"{json.dumps(existing_titles, ensure_ascii=False)}\n\n"
        "=== outline_md ===\n"
        f"{outline_text}\n\n"
        "=== chapter_content_md ===\n"
        f"{chapter_text}\n"
    )
    return system, user


def merge_worldbook_markdown(*, old: str, new: str, mode: str) -> str:
    """
    Helper used by LMEM-641:
    - append_missing: if old is empty -> new else keep old
    - append: append new under old with a separator when both exist
    - replace: always replace with new if new is non-empty
    """

    old_s = (old or "").strip()
    new_s = (new or "").strip()
    mode_norm = str(mode or "").strip().lower() or "append_missing"

    if not new_s:
        return old_s
    if mode_norm == "replace":
        return new_s
    if mode_norm == "append":
        if not old_s:
            return new_s
        return f"{old_s}\n\n---\n\n{new_s}".strip()
    # default: append_missing
    return new_s if not old_s else old_s

