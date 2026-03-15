from __future__ import annotations

import json
import threading
import unittest

from app.services.outline_generation_models import OutlineSegmentGenerationResult
from app.services.outline_generation_stream_finalize_service import (
    finalize_outline_stream_result,
    finalize_segmented_outline_stream_result,
    sanitize_outline_stream_result,
)
from app.services.outline_generation_stream_progress_service import iter_segment_progress_sse_events


class _DoneFuture:
    def done(self) -> bool:
        return True


class TestOutlineStreamHelpers(unittest.TestCase):
    def test_iter_segment_progress_sse_events_emits_preview_chunk_result_and_progress(self) -> None:
        progress_events = [
            {
                "event": "batch_applied",
                "batch_index": 2,
                "batch_count": 4,
                "attempt": 1,
                "completed_count": 8,
                "outline_md": "# 大纲",
                "chapters_snapshot": [{"number": 1, "title": "第一章", "beats": ["事件"]}],
                "raw_output_preview": '{"chapters":[{"number":1}]}',
                "raw_output_chars": 26,
                "progress_percent": 42,
            }
        ]
        events = list(
            iter_segment_progress_sse_events(
                future=_DoneFuture(),
                progress_events=progress_events,
                progress_lock=threading.Lock(),
                heartbeat_interval=1.0,
                poll_interval=0.0,
                progress_message_builder=lambda _snapshot: "分段生成已应用一批结果",
            )
        )

        self.assertGreaterEqual(len(events), 4)
        self.assertEqual(events[0], ": heartbeat\n\n")
        self.assertIn('event: result', events[1])
        self.assertIn('"outline_md": "# 大纲"', events[1])
        self.assertIn('event: token', events[2])
        self.assertIn('[batch_applied | batch 2/4 | attempt 1]', events[2])
        self.assertIn('event: progress', events[3])
        self.assertIn('"message": "分段生成已应用一批结果"', events[3])

    def test_finalize_segmented_outline_stream_result_keeps_generation_metadata(self) -> None:
        segmented = OutlineSegmentGenerationResult(
            data={
                "outline_md": "# 大纲",
                "chapters": [{"number": 1, "title": "第一章", "beats": ["事件"]}],
                "raw_output": "secret",
            },
            warnings=["a", "a", "b"],
            parse_error={"code": "ERR"},
            run_ids=["sub-1", "sub-2"],
            latency_ms=321,
            dropped_params=["temperature"],
            finish_reasons=["length", "stop"],
            meta={"mode": "segmented"},
        )

        result = finalize_segmented_outline_stream_result(
            segmented=segmented,
            aggregate_run_id="agg-1",
            dedupe_warnings=lambda values: list(dict.fromkeys(values)),
        )

        self.assertEqual(result["generation_run_id"], "agg-1")
        self.assertEqual(result["generation_sub_run_ids"], ["sub-1", "sub-2"])
        self.assertEqual(result["generation_run_ids"], ["agg-1", "sub-1", "sub-2"])
        self.assertEqual(result["warnings"], ["a", "b"])
        self.assertEqual(result["parse_error"], {"code": "ERR"})
        self.assertEqual(result["finish_reason"], "stop")
        self.assertEqual(result["finish_reasons"], ["length", "stop"])
        self.assertNotIn("raw_output", result)

    def test_finalize_outline_stream_result_strips_private_fields_and_keeps_parse_error(self) -> None:
        result = finalize_outline_stream_result(
            data={
                "outline_md": "# 大纲",
                "chapters": [],
                "raw_output": "raw",
                "raw_json": json.dumps({"x": 1}, ensure_ascii=False),
                "fixed_json": '{"x":1}',
            },
            warnings=["outline_fix_json_failed", "outline_fix_json_failed"],
            parse_error={"code": "OUTLINE_PARSE_ERROR"},
            finish_reason="length",
            latency_ms=888,
            dropped_params=["top_p"],
            generation_run_id="run-1",
            dedupe_warnings=lambda values: list(dict.fromkeys(values)),
        )

        self.assertEqual(result["warnings"], ["outline_fix_json_failed"])
        self.assertEqual(result["parse_error"], {"code": "OUTLINE_PARSE_ERROR"})
        self.assertEqual(result["finish_reason"], "length")
        self.assertEqual(result["latency_ms"], 888)
        self.assertEqual(result["dropped_params"], ["top_p"])
        self.assertEqual(result["generation_run_id"], "run-1")
        self.assertNotIn("raw_output", result)
        self.assertNotIn("raw_json", result)
        self.assertNotIn("fixed_json", result)

    def test_sanitize_outline_stream_result_removes_private_fields(self) -> None:
        result = sanitize_outline_stream_result({"outline_md": "# 大纲", "raw_output": "x", "raw_json": "{}", "fixed_json": "{}"})
        self.assertEqual(result, {"outline_md": "# 大纲"})


if __name__ == "__main__":
    unittest.main()
