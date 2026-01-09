from __future__ import annotations

import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.errors import AppError
from app.models.generation_run import GenerationRun
from app.models.plot_analysis import PlotAnalysis
from app.models.story_memory import StoryMemory
from app.services.plot_analysis_service import (
    apply_chapter_analysis,
    extract_story_memory_seeds,
    validate_analysis_payload,
)


class TestPlotAnalysisApply(unittest.TestCase):
    def _make_db(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        with engine.begin() as conn:
            conn.exec_driver_sql("PRAGMA foreign_keys=ON;")
            conn.exec_driver_sql("CREATE TABLE users (id VARCHAR(64) PRIMARY KEY)")
            conn.exec_driver_sql("CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY)")
            conn.exec_driver_sql("CREATE TABLE chapters (id VARCHAR(36) PRIMARY KEY)")
            conn.execute(text("INSERT INTO users (id) VALUES (:id)"), {"id": "local-user"})
            conn.execute(text("INSERT INTO projects (id) VALUES (:id)"), {"id": "project-1"})
            conn.execute(text("INSERT INTO chapters (id) VALUES (:id)"), {"id": "chapter-1"})

        GenerationRun.__table__.create(engine)
        PlotAnalysis.__table__.create(engine)
        StoryMemory.__table__.create(engine)
        return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def test_validate_analysis_payload_rejects_non_object(self) -> None:
        with self.assertRaises(AppError) as ctx:
            validate_analysis_payload(["not-a-dict"])  # type: ignore[arg-type]
        self.assertEqual(ctx.exception.code, "ANALYSIS_PARSE_ERROR")

    def test_extract_story_memory_seeds_always_has_chapter_summary(self) -> None:
        seeds = extract_story_memory_seeds(
            chapter_number=3,
            analysis={
                "chapter_summary": "",
                "plot_points": [{"beat": "转折 A", "excerpt": ""}, {"beat": "冲突升级", "excerpt": ""}],
                "hooks": [{"excerpt": "不存在的片段", "note": "钩子说明"}],
            },
            content_md="正文里没有那个片段。",
        )
        self.assertGreaterEqual(len(seeds), 1)
        self.assertEqual(seeds[0]["memory_type"], "chapter_summary")
        self.assertIn("转折 A", str(seeds[0]["content"]))
        hook = next((s for s in seeds if s["memory_type"] == "hook"), None)
        self.assertIsNotNone(hook)
        self.assertEqual(hook["text_position"], -1)
        self.assertEqual(hook["text_length"], 0)

    def test_apply_is_idempotent_and_does_not_duplicate(self) -> None:
        SessionLocal = self._make_db()
        analysis = {
            "chapter_summary": "本章摘要",
            "hooks": [{"excerpt": "ABC", "note": "开头钩子"}],
            "plot_points": [{"beat": "冲突升级", "excerpt": "XYZ"}],
            "foreshadows": [{"excerpt": "", "note": "伏笔"}],
            "character_states": [
                {"character_name": "张三", "state_before": "平静", "state_after": "紧张", "psychological_change": ""}
            ],
        }

        with SessionLocal() as db:
            out1 = apply_chapter_analysis(
                db=db,
                request_id="req-1",
                actor_user_id="local-user",
                project_id="project-1",
                chapter_id="chapter-1",
                chapter_number=1,
                analysis=analysis,
                draft_content_md="ABC ... XYZ",
            )
            self.assertFalse(out1["idempotent"])
            plot_id = out1["plot_analysis_id"]

            ids1 = {m.id for m in db.query(StoryMemory).all()}
            self.assertGreaterEqual(len(ids1), 1)
            self.assertEqual(db.query(PlotAnalysis).count(), 1)
            self.assertEqual(db.query(GenerationRun).filter(GenerationRun.type == "analysis_apply").count(), 1)

            out2 = apply_chapter_analysis(
                db=db,
                request_id="req-2",
                actor_user_id="local-user",
                project_id="project-1",
                chapter_id="chapter-1",
                chapter_number=1,
                analysis=analysis,
                draft_content_md="ABC ... XYZ",
            )
            self.assertTrue(out2["idempotent"])
            self.assertEqual(out2["plot_analysis_id"], plot_id)

            ids2 = {m.id for m in db.query(StoryMemory).all()}
            self.assertEqual(ids1, ids2)
            self.assertEqual(db.query(PlotAnalysis).count(), 1)
            self.assertEqual(db.query(GenerationRun).filter(GenerationRun.type == "analysis_apply").count(), 1)

