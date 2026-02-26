from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.chapter import Chapter
from app.models.generation_run import GenerationRun
from app.models.llm_preset import LLMPreset
from app.models.outline import Outline
from app.models.plot_analysis import PlotAnalysis
from app.models.project import Project
from app.models.project_settings import ProjectSettings
from app.models.story_memory import StoryMemory
from app.models.user import User
from app.services.generation_service import RecordedLlmResult
from app.services.plot_analysis_service import plot_auto_update_v1


def _compact_json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class TestPlotAutoUpdateService(unittest.TestCase):
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
                LLMPreset.__table__,
                PlotAnalysis.__table__,
                StoryMemory.__table__,
                GenerationRun.__table__,
                ProjectSettings.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        with self.SessionLocal() as db:
            db.add(User(id="u1", display_name="u1"))
            db.add(Project(id="p1", owner_user_id="u1", name="P1", genre=None, logline=None))
            db.add(Outline(id="o1", project_id="p1", title="Outline", content_md="outline", structure_json=None))
            db.add(
                Chapter(
                    id="c1",
                    project_id="p1",
                    outline_id="o1",
                    number=1,
                    title="Ch1",
                    plan=None,
                    content_md="Alice meets Bob. Alice looks at a ring.",
                    summary=None,
                    status="done",
                )
            )
            db.add(LLMPreset(project_id="p1", provider="openai", base_url=None, model="gpt-test"))
            db.commit()

    def test_plot_auto_update_v1_applies_story_memories(self) -> None:
        model_out = _compact_json_dumps(
            {
                "chapter_summary": "Summary",
                "hooks": [{"excerpt": "Alice meets Bob.", "note": "Who is Bob?"}],
                "foreshadows": [{"excerpt": "ring", "note": "The ring matters"}],
                "plot_points": [{"beat": "Meet Bob", "excerpt": "Alice meets Bob."}],
                "suggestions": [],
                "overall_notes": "notes",
            }
        )

        with patch("app.services.plot_analysis_service.SessionLocal", self.SessionLocal), patch(
            "app.services.plot_analysis_service.ensure_default_chapter_analyze_preset", return_value=None
        ), patch(
            "app.services.plot_analysis_service.build_chapter_analyze_render_values", return_value={}
        ), patch(
            "app.services.plot_analysis_service.render_preset_for_task",
            return_value=("sys", "user", None, None, None, None, {}),
        ), patch(
            "app.services.plot_analysis_service.resolve_api_key_for_project", return_value="masked_api_key"
        ), patch(
            "app.services.plot_analysis_service.call_llm_and_record_with_retries",
            return_value=(
                RecordedLlmResult(
                    text=model_out,
                    finish_reason=None,
                    latency_ms=1,
                    dropped_params=[],
                    run_id="run-test",
                ),
                [{"attempt": 1, "request_id": "rid-test", "run_id": "run-test"}],
            ),
        ), patch("app.services.plot_analysis_service.schedule_vector_rebuild_task", return_value=None), patch(
            "app.services.plot_analysis_service.schedule_search_rebuild_task", return_value=None
        ):
            res = plot_auto_update_v1(project_id="p1", actor_user_id="u1", request_id="rid-test", chapter_id="c1")

        self.assertTrue(bool(res.get("ok")))

        with self.SessionLocal() as db:
            memories = (
                db.execute(
                    select(StoryMemory).where(StoryMemory.project_id == "p1", StoryMemory.chapter_id == "c1").order_by(StoryMemory.memory_type.asc())
                )
                .scalars()
                .all()
            )
            self.assertTrue(len(memories) >= 1)
            types = {m.memory_type for m in memories}
            self.assertIn("chapter_summary", types)
            self.assertIn("hook", types)
            self.assertIn("plot_point", types)
            self.assertIn("foreshadow", types)
