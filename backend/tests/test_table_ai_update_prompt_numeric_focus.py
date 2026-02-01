from __future__ import annotations

import unittest

from app.models.project_table import ProjectTable
from app.services.table_ai_update_service import build_table_ai_update_prompt_v1


class TestTableAiUpdatePromptNumericFocus(unittest.TestCase):
    def test_prompt_emphasizes_numeric_only_and_kv_value_type(self) -> None:
        table = ProjectTable(
            id="t1",
            project_id="p1",
            table_key="tbl_money",
            name="Money",
            schema_version=1,
            schema_json="{}",
        )
        schema = {
            "version": 1,
            "columns": [
                {"key": "key", "type": "string", "label": "Key", "required": True},
                {"key": "value", "type": "number", "label": "Value", "required": True},
            ],
        }

        system, user = build_table_ai_update_prompt_v1(
            project_id="p1",
            table=table,
            schema=schema,
            existing_rows=[{"id": "r1", "row_index": 0, "data": {"key": "gold", "value": 50}}],
            chapter=None,
            focus="只更新金钱变化，不要编造",
        )

        self.assertIn("可用数字表示的状态变化", system)
        self.assertIn("不要把剧情、人物关系、设定文本写进表格", system)
        self.assertIn("number 字段必须输出 JSON number", system)
        self.assertIn("Key/Value 结构", system)
        self.assertIn("value 字段类型为 number", system)

        self.assertIn("=== table_schema ===", user)
        self.assertIn("=== existing_rows", user)
        self.assertIn("=== focus", user)

