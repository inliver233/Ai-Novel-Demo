from __future__ import annotations

import time
import unittest

from app.utils.sse_response import sse_heartbeat, sse_progress, stream_blocking_call_with_heartbeat


class TestChapterGenerateStreamKeepalive(unittest.TestCase):
    def test_blocking_step_emits_heartbeat_before_return(self) -> None:
        generator = stream_blocking_call_with_heartbeat(
            runner=lambda: (time.sleep(0.05), {"ok": True})[1],
            start_event=sse_progress(message="润色中...", progress=95),
            heartbeat_event=sse_heartbeat(),
            heartbeat_interval_seconds=0.01,
        )

        frames: list[str] = []
        while True:
            try:
                frames.append(next(generator))
            except StopIteration as stop:
                result = stop.value
                break

        self.assertEqual(frames[0], sse_progress(message="润色中...", progress=95))
        self.assertGreaterEqual(frames.count(sse_heartbeat()), 1)
        self.assertEqual(result, {"ok": True})


if __name__ == "__main__":
    unittest.main()
