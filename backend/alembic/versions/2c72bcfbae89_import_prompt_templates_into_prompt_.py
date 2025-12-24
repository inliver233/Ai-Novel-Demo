"""import prompt_templates into prompt_presets and drop table

Revision ID: 2c72bcfbae89
Revises: f078e253d338
Create Date: 2025-12-24 14:34:27.476817

"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = '2c72bcfbae89'
down_revision = 'f078e253d338'
branch_labels = None
depends_on = None


LEGACY_IMPORTED_SCOPE = "legacy_imported"
LEGACY_IMPORTED_PRESET_NAME = "[Migrated] prompt_templates"


def _new_id() -> str:
    return str(uuid4())


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except Exception:
        return []
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item:
            out.append(item)
    return out


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "prompt_templates" not in inspector.get_table_names():
        return

    templates = bind.execute(
        sa.text(
            """
            SELECT project_id, type, system_template, user_template, updated_at
            FROM prompt_templates
            """
        )
    ).mappings().all()

    if templates:
        templates_by_project: dict[str, list[dict]] = {}
        for row in templates:
            project_id = str(row.get("project_id") or "")
            if not project_id:
                continue
            templates_by_project.setdefault(project_id, []).append(dict(row))

        existing_presets = bind.execute(
            sa.text(
                """
                SELECT id, project_id, name, scope, version, active_for_json, created_at, updated_at
                FROM prompt_presets
                WHERE name = :name
                """
            ),
            {"name": LEGACY_IMPORTED_PRESET_NAME},
        ).mappings().all()
        legacy_preset_by_project: dict[str, dict] = {str(r["project_id"]): dict(r) for r in existing_presets if r.get("project_id")}

        now = _utc_now_iso()

        for project_id, rows in templates_by_project.items():
            legacy_preset = legacy_preset_by_project.get(project_id)
            if legacy_preset is None:
                preset_id = _new_id()
                active_for = sorted({str(r.get("type") or "") for r in rows if str(r.get("type") or "")})
                bind.execute(
                    sa.text(
                        """
                        INSERT INTO prompt_presets (id, project_id, name, scope, version, active_for_json, created_at, updated_at)
                        VALUES (:id, :project_id, :name, :scope, :version, :active_for_json, :created_at, :updated_at)
                        """
                    ),
                    {
                        "id": preset_id,
                        "project_id": project_id,
                        "name": LEGACY_IMPORTED_PRESET_NAME,
                        "scope": LEGACY_IMPORTED_SCOPE,
                        "version": 1,
                        "active_for_json": json.dumps(active_for, ensure_ascii=False),
                        "created_at": now,
                        "updated_at": now,
                    },
                )
            else:
                preset_id = str(legacy_preset.get("id") or "")
                if legacy_preset.get("scope") != LEGACY_IMPORTED_SCOPE:
                    bind.execute(
                        sa.text("UPDATE prompt_presets SET scope = :scope WHERE id = :id"),
                        {"scope": LEGACY_IMPORTED_SCOPE, "id": preset_id},
                    )

                prev_active_for = _parse_json_list(legacy_preset.get("active_for_json"))
                merged = sorted(set(prev_active_for) | {str(r.get("type") or "") for r in rows if str(r.get("type") or "")})
                if merged != prev_active_for:
                    bind.execute(
                        sa.text("UPDATE prompt_presets SET active_for_json = :active_for_json WHERE id = :id"),
                        {"active_for_json": json.dumps(merged, ensure_ascii=False), "id": preset_id},
                    )

            blocks = bind.execute(
                sa.text("SELECT identifier FROM prompt_blocks WHERE preset_id = :preset_id"),
                {"preset_id": preset_id},
            ).mappings().all()
            existing_identifiers = {str(b.get("identifier") or "") for b in blocks if b.get("identifier")}

            budget_must = json.dumps({"priority": "must"}, ensure_ascii=False)

            def _insert_block(
                *,
                identifier: str,
                name: str,
                role: str,
                injection_order: int,
                triggers: list[str],
                template: str | None,
            ) -> None:
                bind.execute(
                    sa.text(
                        """
                        INSERT INTO prompt_blocks (
                          id, preset_id, identifier, name, role, enabled, template, marker_key,
                          injection_position, injection_depth, injection_order, triggers_json,
                          forbid_overrides, budget_json, cache_json, created_at, updated_at
                        ) VALUES (
                          :id, :preset_id, :identifier, :name, :role, :enabled, :template, :marker_key,
                          :injection_position, :injection_depth, :injection_order, :triggers_json,
                          :forbid_overrides, :budget_json, :cache_json, :created_at, :updated_at
                        )
                        """
                    ),
                    {
                        "id": _new_id(),
                        "preset_id": preset_id,
                        "identifier": identifier,
                        "name": name,
                        "role": role,
                        "enabled": True,
                        "template": template or "",
                        "marker_key": None,
                        "injection_position": "relative",
                        "injection_depth": None,
                        "injection_order": injection_order,
                        "triggers_json": json.dumps(triggers, ensure_ascii=False),
                        "forbid_overrides": False,
                        "budget_json": budget_must,
                        "cache_json": None,
                        "created_at": now,
                        "updated_at": now,
                    },
                )

            for t in rows:
                task = str(t.get("type") or "").strip()
                if not task:
                    continue

                sys_identifier = f"sys.legacy_system.{task}"
                if sys_identifier not in existing_identifiers:
                    _insert_block(
                        identifier=sys_identifier,
                        name=f"Legacy system ({task})",
                        role="system",
                        injection_order=10,
                        triggers=[task],
                        template=str(t.get("system_template") or ""),
                    )
                    existing_identifiers.add(sys_identifier)

                user_identifier = f"user.legacy_user.{task}"
                if user_identifier not in existing_identifiers:
                    _insert_block(
                        identifier=user_identifier,
                        name=f"Legacy user ({task})",
                        role="user",
                        injection_order=20,
                        triggers=[task],
                        template=str(t.get("user_template") or ""),
                    )
                    existing_identifiers.add(user_identifier)

    op.drop_table("prompt_templates")


def downgrade() -> None:
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("system_template", sa.Text(), nullable=True),
        sa.Column("user_template", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "type", name="uq_prompt_templates_project_id_type"),
    )
    with op.batch_alter_table("prompt_templates", schema=None) as batch_op:
        batch_op.create_index("ix_prompt_templates_project_id", ["project_id"], unique=False)

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "prompt_presets" not in inspector.get_table_names() or "prompt_blocks" not in inspector.get_table_names():
        return

    presets = bind.execute(
        sa.text(
            """
            SELECT id, project_id
            FROM prompt_presets
            WHERE scope = :scope
            """
        ),
        {"scope": LEGACY_IMPORTED_SCOPE},
    ).mappings().all()
    if not presets:
        return

    now = _utc_now_iso()
    for preset in presets:
        preset_id = str(preset.get("id") or "")
        project_id = str(preset.get("project_id") or "")
        if not preset_id or not project_id:
            continue

        blocks = bind.execute(
            sa.text("SELECT identifier, role, template FROM prompt_blocks WHERE preset_id = :preset_id"),
            {"preset_id": preset_id},
        ).mappings().all()

        by_task: dict[str, dict[str, str]] = {}
        for b in blocks:
            ident = str(b.get("identifier") or "")
            if ident.startswith("sys.legacy_system."):
                task = ident.removeprefix("sys.legacy_system.").strip()
                if task:
                    by_task.setdefault(task, {})["system_template"] = str(b.get("template") or "")
            elif ident.startswith("user.legacy_user."):
                task = ident.removeprefix("user.legacy_user.").strip()
                if task:
                    by_task.setdefault(task, {})["user_template"] = str(b.get("template") or "")

        for task, pair in by_task.items():
            bind.execute(
                sa.text(
                    """
                    INSERT INTO prompt_templates (id, project_id, type, system_template, user_template, updated_at)
                    VALUES (:id, :project_id, :type, :system_template, :user_template, :updated_at)
                    """
                ),
                {
                    "id": _new_id(),
                    "project_id": project_id,
                    "type": task,
                    "system_template": pair.get("system_template") or "",
                    "user_template": pair.get("user_template") or "",
                    "updated_at": now,
                },
            )

