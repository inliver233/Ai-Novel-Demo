from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.models.chapter import Chapter
from app.services.fractal_memory_service import FractalConfig, compute_fractal


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

