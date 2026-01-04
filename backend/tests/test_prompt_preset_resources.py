import unittest

from app.services.prompt_preset_resources import load_preset_resource


class TestPromptPresetResources(unittest.TestCase):
    def test_builtin_resources_load_and_validate(self) -> None:
        keys = [
            "plan_chapter_v1",
            "post_edit_v1",
            "outline_generate_v3",
            "chapter_generate_v3",
            "chapter_analyze_v1",
            "chapter_rewrite_v1",
        ]

        for key in keys:
            res = load_preset_resource(key)
            self.assertEqual(res.key, key)
            self.assertTrue(res.name)
            self.assertGreater(res.version, 0)
            self.assertGreater(len(res.blocks), 0)


if __name__ == "__main__":
    unittest.main()

