from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.db.base import Base
from app.models.project import Project
from app.models.prompt_block import PromptBlock
from app.models.prompt_preset import PromptPreset
from app.models.user import User
from app.services.prompt_preset_canary import run_prompt_preset_canaries
from app.services.prompt_preset_integrity import collect_prompt_preset_integrity
from app.services.prompt_presets import _ensure_default_preset_from_resource
from scripts.guards.base import build_context
from scripts.guards.prompt_preset_integrity_guard import GUARD_ID, run as run_prompt_guard
from scripts.guards.registry import REGISTRY


class TestPromptPresetIntegrity(unittest.TestCase):
    def test_default_resources_pass_integrity_and_canary(self) -> None:
        report = collect_prompt_preset_integrity()
        self.assertEqual(report.issues, ())
        self.assertGreater(len(report.checked_resources), 0)
        self.assertGreater(len(report.canaries), 0)
        self.assertTrue(all(result.passed for result in report.canaries))

    def test_integrity_detects_missing_template_and_orphan_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            resource_dir = base_dir / "demo_resource_v1"
            templates_dir = resource_dir / "templates"
            templates_dir.mkdir(parents=True)
            (templates_dir / "used.md").write_text("Hello {{name}}", encoding="utf-8")
            (templates_dir / "orphan.md").write_text("orphan", encoding="utf-8")
            (resource_dir / "preset.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "name": "Demo",
                        "category": "demo",
                        "scope": "project",
                        "version": 1,
                        "activation_tasks": ["demo_task"],
                        "upgrade_add_identifiers": ["missing.block"],
                        "blocks": [
                            {
                                "identifier": "sys.demo.role",
                                "name": "Demo role",
                                "role": "system",
                                "enabled": True,
                                "template_file": "templates/missing.md",
                                "marker_key": "bad marker",
                                "injection_position": "relative",
                                "injection_depth": None,
                                "injection_order": 10,
                                "triggers": ["other_task", "other_task"],
                                "forbid_overrides": False,
                                "budget": {"priority": "urgent"},
                                "cache": None,
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            report = collect_prompt_preset_integrity(base_dir=base_dir, include_canaries=False)
            messages = [issue.message for issue in report.issues]
            self.assertTrue(any("template file missing" in message for message in messages))
            self.assertTrue(any("invalid marker_key" in message for message in messages))
            self.assertTrue(any("duplicate trigger" in message for message in messages))
            self.assertTrue(any("not declared in activation_tasks" in message for message in messages))
            self.assertTrue(any("invalid budget priority" in message for message in messages))
            self.assertTrue(any("upgrade_add_identifier missing block definition" in message for message in messages))
            self.assertTrue(any("template file is not referenced" in message for message in messages))

    def test_guard_registered_and_passes(self) -> None:
        self.assertIn(GUARD_ID, REGISTRY)
        result = run_prompt_guard(build_context())
        self.assertFalse(result.has_errors, msg=str(result.findings))


class TestPromptPresetDefaultUpgradeBehavior(unittest.TestCase):
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
                PromptPreset.__table__,
                PromptBlock.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        with self.SessionLocal() as db:
            db.add(User(id="u1", display_name="owner"))
            db.add(Project(id="p1", owner_user_id="u1", name="Project 1", genre=None, logline=None))
            db.commit()

    def test_ensure_default_preset_does_not_silently_restore_removed_upgrade_block_when_version_unchanged(self) -> None:
        with self.SessionLocal() as db:
            preset = _ensure_default_preset_from_resource(db, project_id="p1", resource_key="chapter_generate_v4", activate=True)
            deleted = db.execute(
                select(PromptBlock).where(
                    PromptBlock.preset_id == preset.id,
                    PromptBlock.identifier == "sys.story.append_rules",
                )
            ).scalar_one()
            customized = db.execute(
                select(PromptBlock).where(
                    PromptBlock.preset_id == preset.id,
                    PromptBlock.identifier == "sys.chapter.core_role",
                )
            ).scalar_one()
            customized.template = "custom override"
            db.delete(deleted)
            db.commit()

            again = _ensure_default_preset_from_resource(db, project_id="p1", resource_key="chapter_generate_v4", activate=True)
            self.assertEqual(again.id, preset.id)
            restored = db.execute(
                select(PromptBlock).where(
                    PromptBlock.preset_id == preset.id,
                    PromptBlock.identifier == "sys.story.append_rules",
                )
            ).scalar_one_or_none()
            self.assertIsNone(restored)
            kept = db.execute(
                select(PromptBlock).where(
                    PromptBlock.preset_id == preset.id,
                    PromptBlock.identifier == "sys.chapter.core_role",
                )
            ).scalar_one()
            self.assertEqual(kept.template, "custom override")

    def test_ensure_default_preset_applies_upgrade_additions_when_version_is_older(self) -> None:
        with self.SessionLocal() as db:
            preset = _ensure_default_preset_from_resource(db, project_id="p1", resource_key="chapter_generate_v4", activate=True)
            deleted = db.execute(
                select(PromptBlock).where(
                    PromptBlock.preset_id == preset.id,
                    PromptBlock.identifier == "sys.story.append_rules",
                )
            ).scalar_one()
            db.delete(deleted)
            preset.version = 3
            db.commit()

            again = _ensure_default_preset_from_resource(db, project_id="p1", resource_key="chapter_generate_v4", activate=True)
            self.assertEqual(again.version, 4)
            restored = db.execute(
                select(PromptBlock).where(
                    PromptBlock.preset_id == preset.id,
                    PromptBlock.identifier == "sys.story.append_rules",
                )
            ).scalar_one_or_none()
            self.assertIsNotNone(restored)


if __name__ == "__main__":
    unittest.main()
