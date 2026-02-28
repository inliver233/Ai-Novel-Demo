from __future__ import annotations

import unittest

from app.services.table_ai_update_service import parse_table_update_output_v1
from app.services.table_executor import TableUpdateV1Request


class TestTableUpdateV1OpsEmpty(unittest.TestCase):
    def test_parse_allows_empty_ops_as_noop(self) -> None:
        data, warnings, parse_error = parse_table_update_output_v1(
            '{"title":"t","summary_md":"s","ops":[]}',
            expected_table_id="t1",
            finish_reason=None,
        )
        self.assertIsNone(parse_error)
        self.assertIn("ops_empty", warnings)
        self.assertEqual(len(data.get("ops") or []), 0)

    def test_request_allows_empty_ops(self) -> None:
        payload = TableUpdateV1Request(
            schema_version="table_update_v1",
            idempotency_key="idem-12345678",
            title=None,
            summary_md=None,
            ops=[],
        )
        self.assertEqual(len(payload.ops), 0)

