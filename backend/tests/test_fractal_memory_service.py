from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.chapter import Chapter
from app.models.fractal_memory import FractalMemory
from app.models.outline import Outline
from app.models.project import Project
from app.models.story_memory import StoryMemory
from app.models.user import User
from app.services.fractal_memory_service import (
    FractalConfig,
    compute_fractal,
    get_fractal_context,
    rebuild_fractal_memory,
    rebuild_fractal_memory_v2,
)


class TestFractalMemoryService(unittest.TestCase):
    def test_compute_is_deterministic(self) -> None:
        t = datetime(2026, 1, 1, tzinfo=timezone.utc)
        chapters = [
            Chapter(
                id="c1",
                project_id="p1",
                outline_id="o1",
                number=1,
                title="第一章",
                plan=None,
                content_md="Alice meets Bob.",
                summary=None,
                status="done",
                updated_at=t,
            ),
            Chapter(
                id="c2",
                project_id="p1",
                outline_id="o1",
                number=2,
                title="第二章",
                plan=None,
                content_md="They become friends.",
                summary="简要：成为朋友。",
                status="done",
                updated_at=t,
            ),
        ]
        cfg = FractalConfig(scene_window=5, arc_window=5, char_limit=6000)
        a = compute_fractal(chapters=chapters, config=cfg)
        b = compute_fractal(chapters=chapters, config=cfg)
        self.assertEqual(a["prompt_block"]["text_md"], b["prompt_block"]["text_md"])
        self.assertEqual(len(a["scenes"]), 2)
        self.assertEqual(len(a["arcs"]), 1)
        self.assertEqual(len(a["sagas"]), 1)

    def test_scene_window_groups_arcs(self) -> None:
        t = datetime(2026, 1, 1, tzinfo=timezone.utc)
        chapters = [
            Chapter(
                id=f"c{i}",
                project_id="p1",
                outline_id="o1",
                number=i,
                title=f"第{i}章",
                plan=None,
                content_md=f"scene {i}",
                summary=None,
                status="done",
                updated_at=t,
            )
            for i in range(1, 6)
        ]
        cfg = FractalConfig(scene_window=2, arc_window=5, char_limit=6000)
        out = compute_fractal(chapters=chapters, config=cfg)
        self.assertEqual(len(out["scenes"]), 5)
        self.assertEqual(len(out["arcs"]), 3)


class TestFractalMemoryStorageLoop(unittest.TestCase):
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
                Outline.__table__,
                Chapter.__table__,
                FractalMemory.__table__,
                StoryMemory.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _seed_project(self, *, db, chapter_count: int) -> None:
        db.add(User(id="u1", display_name="User 1", is_admin=False))
        db.add(Project(id="p1", owner_user_id="u1", name="Project 1", genre=None, logline=None))
        db.add(Outline(id="o1", project_id="p1", title="Outline 1", content_md=None, structure_json=None))
        db.bulk_save_objects(
            [
                Chapter(
                    id=f"c{i}",
                    project_id="p1",
                    outline_id="o1",
                    number=i,
                    title=f"第{i}章",
                    plan=None,
                    content_md=f"scene {i}",
                    summary=None,
                    status="done",
                )
                for i in range(1, chapter_count + 1)
            ]
        )
        db.commit()

    def test_rebuild_then_get_roundtrip(self) -> None:
        with self.SessionLocal() as db:
            self._seed_project(db=db, chapter_count=2)
            db.add(
                StoryMemory(
                    id="m1",
                    project_id="p1",
                    chapter_id="c1",
                    memory_type="chapter_summary",
                    title=None,
                    content="摘要：plot_analysis chapter_summary",
                    full_context_md=None,
                    importance_score=1.0,
                    tags_json=None,
                    story_timeline=1,
                )
            )
            db.commit()

            rebuilt = rebuild_fractal_memory(db=db, project_id="p1", reason="test_roundtrip")
            fetched = get_fractal_context(db=db, project_id="p1", enabled=True)

        self.assertTrue(rebuilt.get("enabled"))
        self.assertTrue(fetched.get("enabled"))
        self.assertEqual(rebuilt.get("prompt_block"), fetched.get("prompt_block"))
        self.assertEqual(rebuilt.get("config"), fetched.get("config"))

        cfg = fetched.get("config") or {}
        self.assertEqual(cfg.get("reason"), "test_roundtrip")
        self.assertEqual(cfg.get("done_chapters_total"), 2)
        self.assertEqual(cfg.get("done_chapters_used"), 2)
        self.assertFalse(bool(cfg.get("done_chapters_truncated")))
        scenes = list(rebuilt.get("scenes") or [])
        self.assertTrue(scenes)
        self.assertEqual(str(scenes[0].get("summary_md") or ""), "摘要：plot_analysis chapter_summary")

    def test_rebuild_caps_done_chapters_with_observable_config(self) -> None:
        with self.SessionLocal() as db:
            self._seed_project(db=db, chapter_count=260)
            out = rebuild_fractal_memory(db=db, project_id="p1", reason="test_cap")

        cfg = out.get("config") or {}
        self.assertEqual(cfg.get("reason"), "test_cap")
        self.assertEqual(cfg.get("done_chapters_total"), 260)
        self.assertTrue(bool(cfg.get("done_chapters_truncated")))
        self.assertIsInstance(cfg.get("done_chapters_limit"), int)
        self.assertIsInstance(cfg.get("done_chapters_used"), int)
        self.assertEqual(cfg.get("done_chapters_used"), cfg.get("done_chapters_limit"))

        scenes = list(out.get("scenes") or [])
        self.assertEqual(len(scenes), int(cfg.get("done_chapters_used") or 0))
        self.assertEqual(int(scenes[0].get("chapter_number") or 0), 61)

    def test_rebuild_v2_fallback_when_llm_preset_missing(self) -> None:
        with self.SessionLocal() as db:
            self._seed_project(db=db, chapter_count=3)
            out = rebuild_fractal_memory_v2(
                db=db,
                project_id="p1",
                reason="test_v2_missing",
                request_id="rid-test-v2-missing",
                actor_user_id="u1",
                api_key="",
                llm_call=None,
            )

        self.assertTrue(bool(out.get("enabled")))
        self.assertIsNone(out.get("disabled_reason"))
        v2 = out.get("v2") or {}
        self.assertFalse(bool(v2.get("enabled")))
        self.assertEqual(v2.get("status"), "fallback")
        self.assertEqual(v2.get("disabled_reason"), "llm_preset_missing")
        prompt_block_v2 = out.get("prompt_block_v2") or {}
        self.assertEqual(prompt_block_v2.get("identifier"), "sys.memory.fractal_v2")
        self.assertEqual(prompt_block_v2.get("role"), "system")
        self.assertEqual(prompt_block_v2.get("text_md"), "")
