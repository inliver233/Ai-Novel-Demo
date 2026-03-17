from __future__ import annotations

import json
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.prompt_route_helpers import (
    _build_prompt_preset_list_payload,
    _build_prompt_preset_resources_payload,
    _reorder_prompt_blocks_payload,
)
from app.api.routes.prompt_route_import_export import _build_prompt_import_all_payload
from app.api.routes.prompt_route_preview import _build_prompt_preview_response
from app.core.errors import AppError
from app.db.base import Base
from app.models.llm_preset import LLMPreset
from app.models.project import Project
from app.models.prompt_block import PromptBlock
from app.models.prompt_preset import PromptPreset
from app.models.user import User
from app.schemas.prompt_presets import PromptPresetImportAllRequest, PromptPreviewRequest


class TestPromptRouteHelpers(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(
            engine,
            tables=[
                User.__table__,
                Project.__table__,
                LLMPreset.__table__,
                PromptPreset.__table__,
                PromptBlock.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        with self.SessionLocal() as db:
            db.add(User(id="u1", display_name="User 1"))
            db.add(Project(id="p1", owner_user_id="u1", name="Project 1", genre=None, logline=None))
            db.commit()

    def test_list_payload_ensures_baseline_and_resource_join(self) -> None:
        with self.SessionLocal() as db:
            payload = _build_prompt_preset_list_payload(db, project_id="p1")
            presets = payload["presets"]
            self.assertTrue(any(str(item.get("resource_key") or "") == "plan_chapter_v1" for item in presets))

            resource_payload = _build_prompt_preset_resources_payload(db, project_id="p1")
            resources = resource_payload["resources"]
            plan_resource = next((item for item in resources if item.get("key") == "plan_chapter_v1"), None)
            self.assertIsNotNone(plan_resource)
            self.assertTrue(str((plan_resource or {}).get("preset_id") or "").strip())

    def test_reorder_payload_requires_complete_block_set(self) -> None:
        with self.SessionLocal() as db:
            preset = PromptPreset(
                id="preset-1",
                project_id="p1",
                name="Preset 1",
                scope="project",
                version=1,
                active_for_json=json.dumps(["chapter_generate"], ensure_ascii=False),
            )
            db.add(preset)
            db.add_all(
                [
                    PromptBlock(
                        id="block-1",
                        preset_id="preset-1",
                        identifier="sys.one",
                        name="One",
                        role="system",
                        enabled=True,
                        template="A",
                        marker_key=None,
                        injection_position="relative",
                        injection_depth=None,
                        injection_order=0,
                        triggers_json="[]",
                        forbid_overrides=False,
                        budget_json=None,
                        cache_json=None,
                    ),
                    PromptBlock(
                        id="block-2",
                        preset_id="preset-1",
                        identifier="sys.two",
                        name="Two",
                        role="system",
                        enabled=True,
                        template="B",
                        marker_key=None,
                        injection_position="relative",
                        injection_depth=None,
                        injection_order=1,
                        triggers_json="[]",
                        forbid_overrides=False,
                        budget_json=None,
                        cache_json=None,
                    ),
                ]
            )
            db.commit()

            with self.assertRaises(AppError) as ctx:
                _reorder_prompt_blocks_payload(db, preset=preset, ordered_block_ids=["block-1"])
            self.assertIn("expected=2 got=1", str(ctx.exception.message))

            payload = _reorder_prompt_blocks_payload(
                db,
                preset=preset,
                ordered_block_ids=["block-2", "block-1"],
            )
            blocks = payload["blocks"]
            self.assertEqual([item["id"] for item in blocks], ["block-2", "block-1"])

    def test_import_all_payload_tracks_conflicts_and_apply_updates(self) -> None:
        with self.SessionLocal() as db:
            db.add_all(
                [
                    PromptPreset(
                        id="dup-1",
                        project_id="p1",
                        name="Duplicate",
                        scope="project",
                        version=1,
                        active_for_json="[]",
                    ),
                    PromptPreset(
                        id="dup-2",
                        project_id="p1",
                        name="Duplicate",
                        scope="project",
                        version=2,
                        active_for_json="[]",
                    ),
                    PromptPreset(
                        id="existing-1",
                        project_id="p1",
                        name="Existing",
                        scope="project",
                        version=1,
                        active_for_json=json.dumps(["chapter_generate"], ensure_ascii=False),
                    ),
                ]
            )
            db.add(
                PromptBlock(
                    id="existing-block",
                    preset_id="existing-1",
                    identifier="sys.old",
                    name="Old",
                    role="system",
                    enabled=True,
                    template="old",
                    marker_key=None,
                    injection_position="relative",
                    injection_depth=None,
                    injection_order=0,
                    triggers_json="[]",
                    forbid_overrides=False,
                    budget_json=None,
                    cache_json=None,
                )
            )
            db.commit()

            dry_run = PromptPresetImportAllRequest.model_validate(
                {
                    "schema_version": "prompt_presets_export_all_v1",
                    "dry_run": True,
                    "presets": [
                        {
                            "preset": {
                                "name": "Duplicate",
                                "scope": "project",
                                "version": 5,
                                "category": "dup",
                                "active_for": [],
                            },
                            "blocks": [],
                        },
                        {
                            "preset": {
                                "name": "Existing",
                                "scope": "project",
                                "version": 9,
                                "category": "updated",
                                "active_for": ["chapter_generate"],
                            },
                            "blocks": [
                                {
                                    "identifier": "sys.new",
                                    "name": "New",
                                    "role": "system",
                                    "enabled": True,
                                    "template": "hello {{name}}",
                                    "marker_key": None,
                                    "injection_position": "relative",
                                    "injection_depth": None,
                                    "injection_order": 0,
                                    "triggers": ["chapter_generate"],
                                    "forbid_overrides": False,
                                    "budget": {},
                                    "cache": {},
                                }
                            ],
                        },
                        {
                            "preset": {
                                "name": "Created",
                                "scope": "project",
                                "version": 1,
                                "category": "new",
                                "active_for": [],
                            },
                            "blocks": [],
                        },
                    ],
                }
            )
            dry_run_payload = _build_prompt_import_all_payload(db, project_id="p1", body=dry_run)
            self.assertTrue(dry_run_payload["dry_run"])
            self.assertEqual(dry_run_payload["created"], 1)
            self.assertEqual(dry_run_payload["updated"], 1)
            self.assertEqual(dry_run_payload["skipped"], 1)
            self.assertEqual(len(dry_run_payload["conflicts"]), 1)

            apply_body = dry_run.model_copy(update={"dry_run": False})
            apply_payload = _build_prompt_import_all_payload(db, project_id="p1", body=apply_body)
            self.assertFalse(apply_payload["dry_run"])

        with self.SessionLocal() as db:
            updated = db.get(PromptPreset, "existing-1")
            self.assertEqual(updated.version, 9)
            updated_blocks = db.execute(select(PromptBlock).where(PromptBlock.preset_id == "existing-1")).scalars().all()
            self.assertEqual([block.identifier for block in updated_blocks], ["sys.new"])

            created = (
                db.execute(select(PromptPreset).where(PromptPreset.project_id == "p1", PromptPreset.name == "Created"))
                .scalars()
                .one()
            )
            self.assertEqual(created.category, "new")

    def test_preview_response_maps_render_output(self) -> None:
        with self.SessionLocal() as db:
            preset = PromptPreset(
                id="preview-preset",
                project_id="p1",
                name="Preview",
                scope="project",
                version=1,
                active_for_json=json.dumps(["chapter_generate"], ensure_ascii=False),
            )
            db.add(preset)
            db.add(
                PromptBlock(
                    id="preview-block",
                    preset_id="preview-preset",
                    identifier="sys.preview",
                    name="Preview block",
                    role="system",
                    enabled=True,
                    template="Hello {{name}}",
                    marker_key=None,
                    injection_position="relative",
                    injection_depth=None,
                    injection_order=0,
                    triggers_json=json.dumps(["chapter_generate"], ensure_ascii=False),
                    forbid_overrides=False,
                    budget_json=None,
                    cache_json=None,
                )
            )
            db.commit()

            body = PromptPreviewRequest.model_validate(
                {
                    "task": "chapter_generate",
                    "preset_id": "preview-preset",
                    "values": {"name": "Alice"},
                }
            )
            payload = _build_prompt_preview_response(db, project_id="p1", request_id="rid-test", body=body)

        preview = payload["preview"]
        self.assertEqual(preview["preset_id"], "preview-preset")
        self.assertEqual(preview["task"], "chapter_generate")
        self.assertGreaterEqual(preview["prompt_tokens_estimate"], 0)
        self.assertEqual(preview["blocks"][0]["identifier"], "sys.preview")
        self.assertIn("render_log", payload)


if __name__ == "__main__":
    unittest.main()
