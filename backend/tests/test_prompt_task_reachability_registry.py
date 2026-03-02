from __future__ import annotations

import unittest
from pathlib import Path

from app.services.prompt_task_catalog import PROMPT_TASK_CATALOG, PROMPT_TASK_KEYS


class TestPromptTaskReachabilityRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.frontend_catalog_path = cls.repo_root / "frontend" / "src" / "lib" / "promptTaskCatalog.ts"
        cls.ui_copy_path = cls.repo_root / "frontend" / "src" / "lib" / "uiCopy.ts"

    def test_backend_catalog_keys_unique(self) -> None:
        self.assertGreater(len(PROMPT_TASK_KEYS), 0)
        self.assertEqual(len(PROMPT_TASK_KEYS), len(set(PROMPT_TASK_KEYS)))

    def test_frontend_prompt_task_catalog_covers_backend_tasks(self) -> None:
        text = self.frontend_catalog_path.read_text(encoding="utf-8")
        for task in PROMPT_TASK_CATALOG:
            self.assertIn(f'key: "{task.key}"', text)

    def test_ui_copy_and_e2e_registry_registered(self) -> None:
        ui_copy_text = self.ui_copy_path.read_text(encoding="utf-8")
        e2e_cache: dict[Path, str] = {}
        for task in PROMPT_TASK_CATALOG:
            self.assertIn(f"{task.ui_copy_key}:", ui_copy_text)
            self.assertGreater(len(task.e2e_specs), 0)
            for rel_spec in task.e2e_specs:
                spec_path = self.repo_root / rel_spec
                self.assertTrue(spec_path.exists(), msg=f"missing e2e spec: {rel_spec}")
                if spec_path not in e2e_cache:
                    e2e_cache[spec_path] = spec_path.read_text(encoding="utf-8")
                self.assertIn(f'"{task.key}"', e2e_cache[spec_path], msg=f"task {task.key} missing in {rel_spec}")


if __name__ == "__main__":
    unittest.main()
