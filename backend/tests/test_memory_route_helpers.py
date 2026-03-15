from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.api.routes.memory_route_helpers import (
    _build_memory_pack_payload,
    _normalize_memory_auto_propose_args,
    _parse_iso_dt,
    _safe_json,
)


class TestMemoryRouteHelpers(unittest.TestCase):
    def test_safe_json_returns_default_on_bad_input(self) -> None:
        self.assertEqual(_safe_json('{"x": 1}', {}), {"x": 1})
        self.assertEqual(_safe_json("not-json", {"fallback": True}), {"fallback": True})
        self.assertEqual(_safe_json(None, []), [])

    def test_parse_iso_dt_handles_z_suffix_and_invalid_input(self) -> None:
        dt = _parse_iso_dt("2026-03-15T12:00:00Z")
        self.assertIsNotNone(dt)
        assert dt is not None
        self.assertEqual(dt.isoformat(), "2026-03-15T12:00:00+00:00")
        self.assertIsNone(_parse_iso_dt("bad-value"))
        self.assertIsNone(_parse_iso_dt(None))

    def test_normalize_memory_auto_propose_args_trims_and_generates_default_key(self) -> None:
        focus, key = _normalize_memory_auto_propose_args(focus="  protagonist  ", idempotency_key=" idem-1 ")
        self.assertEqual(focus, "protagonist")
        self.assertEqual(key, "idem-1")

        focus2, key2 = _normalize_memory_auto_propose_args(focus="  ", idempotency_key=" ")
        self.assertEqual(focus2, "")
        self.assertRegex(key2, r"^memupd-auto-[a-z0-9]{8}$")

    def test_build_memory_pack_payload_uses_model_dump(self) -> None:
        pack = SimpleNamespace(model_dump=lambda: {"worldbook": {"enabled": True}, "logs": []})
        self.assertEqual(_build_memory_pack_payload(pack), {"worldbook": {"enabled": True}, "logs": []})


if __name__ == "__main__":
    unittest.main()
