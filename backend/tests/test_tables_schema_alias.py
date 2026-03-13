from __future__ import annotations

import unittest

from app.api.routes.tables import TableCreateRequest, TableUpdateRequest


class TestTablesSchemaAlias(unittest.TestCase):
    def test_create_request_accepts_schema_alias(self) -> None:
        schema = {"version": 1, "columns": [{"key": "item", "type": "string", "required": True}]}
        body = TableCreateRequest.model_validate({"name": "Inventory", "schema": schema})
        self.assertEqual(body.table_schema, schema)
        dumped = body.model_dump(by_alias=True)
        self.assertEqual(dumped["schema"], schema)
        self.assertNotIn("table_schema", dumped)

    def test_update_request_accepts_schema_alias(self) -> None:
        schema = {"version": 2, "columns": [{"key": "qty", "type": "number", "required": False}]}
        body = TableUpdateRequest.model_validate({"schema": schema})
        self.assertEqual(body.table_schema, schema)
        dumped = body.model_dump(by_alias=True)
        self.assertEqual(dumped["schema"], schema)
        self.assertNotIn("table_schema", dumped)


if __name__ == "__main__":
    unittest.main()
