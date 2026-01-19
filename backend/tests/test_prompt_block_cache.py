from __future__ import annotations

import json
import time
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.llm_preset import LLMPreset
from app.models.project import Project
from app.models.prompt_block import PromptBlock
from app.models.prompt_preset import PromptPreset
from app.models.user import User
from app.services.prompt_presets import (
    _prompt_block_render_cache,
    _prompt_block_render_cache_lock,
    render_preset_for_task,
)


class TestPromptBlockCache(unittest.TestCase):
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
            db.add(User(id="u1", display_name="User 1", is_admin=True))
            db.add(Project(id="p1", owner_user_id="u1", name="Project 1", genre=None, logline=None))
            db.commit()

        with _prompt_block_render_cache_lock:
            _prompt_block_render_cache.clear()

    def _setup_preset(self, db, *, cache_json: dict) -> str:
        preset_id = "preset1"
        db.add(
            PromptPreset(
                id=preset_id,
                project_id="p1",
                name="Preset 1",
                scope="project",
                version=1,
                active_for_json=json.dumps(["chapter_generate"], ensure_ascii=False),
            )
        )
        db.add(
            PromptBlock(
                id="b1",
                preset_id=preset_id,
                identifier="sys.test.cached",
                name="Cached block",
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
                cache_json=json.dumps(cache_json, ensure_ascii=False),
            )
        )
        db.commit()
        return preset_id

    def test_cache_records_hit_after_miss(self) -> None:
        with self.SessionLocal() as db:
            preset_id = self._setup_preset(db, cache_json={"enabled": True, "key_strategy": "values", "ttl_seconds": 60})

            _, _, _, _, _, _, render_log1 = render_preset_for_task(
                db,
                project_id="p1",
                task="chapter_generate",
                values={"name": "Alice"},
                preset_id=preset_id,
            )
            self.assertEqual(render_log1.get("cache_hit"), [])
            self.assertEqual(len(render_log1.get("cache_miss") or []), 1)

            _, _, _, _, _, _, render_log2 = render_preset_for_task(
                db,
                project_id="p1",
                task="chapter_generate",
                values={"name": "Alice"},
                preset_id=preset_id,
            )
            self.assertEqual(len(render_log2.get("cache_hit") or []), 1)
            self.assertEqual(render_log2.get("cache_miss"), [])

    def test_cache_expires_by_ttl(self) -> None:
        with self.SessionLocal() as db:
            preset_id = self._setup_preset(db, cache_json={"enabled": True, "key_strategy": "values", "ttl_seconds": 1})

            _, _, _, _, _, _, render_log1 = render_preset_for_task(
                db,
                project_id="p1",
                task="chapter_generate",
                values={"name": "Alice"},
                preset_id=preset_id,
            )
            self.assertEqual(render_log1.get("cache_hit"), [])
            self.assertEqual(len(render_log1.get("cache_miss") or []), 1)

            with _prompt_block_render_cache_lock:
                keys = list(_prompt_block_render_cache.keys())
                self.assertEqual(len(keys), 1)
                key = keys[0]
                created_at, payload = _prompt_block_render_cache[key]
                _prompt_block_render_cache[key] = (time.time() - 10, payload)

            _, _, _, _, _, _, render_log2 = render_preset_for_task(
                db,
                project_id="p1",
                task="chapter_generate",
                values={"name": "Alice"},
                preset_id=preset_id,
            )
            self.assertEqual(render_log2.get("cache_hit"), [])
            misses = list(render_log2.get("cache_miss") or [])
            self.assertEqual(len(misses), 1)
            self.assertEqual(str(misses[0].get("reason") or ""), "expired")


if __name__ == "__main__":
    unittest.main()

