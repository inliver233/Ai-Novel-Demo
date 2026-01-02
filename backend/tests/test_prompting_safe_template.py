import os
import unittest

from app.services.prompting import render_template


class TestPromptingSafeTemplate(unittest.TestCase):
    def test_basic_substitution(self) -> None:
        text, missing, err = render_template("Hello {{name}}", {"name": "Alice"})
        self.assertEqual(text, "Hello Alice")
        self.assertEqual(missing, [])
        self.assertIsNone(err)

    def test_if_block_truthy(self) -> None:
        template = "{% if world_setting %}WS={{world_setting}}{% endif %}"
        text, missing, err = render_template(template, {"world_setting": "X"})
        self.assertEqual(text, "WS=X")
        self.assertEqual(missing, [])
        self.assertIsNone(err)

    def test_if_block_falsy(self) -> None:
        template = "{% if world_setting %}WS={{world_setting}}{% endif %}"
        text, missing, err = render_template(template, {"world_setting": ""})
        self.assertEqual(text, "")
        self.assertEqual(missing, [])
        self.assertIsNone(err)

    def test_if_else_and_dotted_path(self) -> None:
        template = "{% if story and story.raw_content %}{{story.raw_content}}{% else %}{{raw_content}}{% endif %}"
        text, missing, err = render_template(template, {"story": {"raw_content": "S"}, "raw_content": "R"})
        self.assertEqual(text, "S")
        self.assertEqual(missing, [])
        self.assertIsNone(err)

    def test_in_operator_with_or(self) -> None:
        template = "{% if 'a' in g or 'b' in g %}YES{% endif %}"
        text1, _, _ = render_template(template, {"g": "xxbxx"})
        text2, _, _ = render_template(template, {"g": "xx"})
        self.assertEqual(text1, "YES")
        self.assertEqual(text2, "")

    def test_eq_operator(self) -> None:
        template = "{% if mode == 'append' %}APPEND{% else %}REPLACE{% endif %}"
        text1, missing1, err1 = render_template(template, {"mode": "append"})
        text2, missing2, err2 = render_template(template, {"mode": "replace"})
        self.assertEqual(text1, "APPEND")
        self.assertEqual(text2, "REPLACE")
        self.assertEqual(missing1, [])
        self.assertEqual(missing2, [])
        self.assertIsNone(err1)
        self.assertIsNone(err2)

    def test_macros_are_supported(self) -> None:
        text, _, err = render_template("Today={{date}}", {})
        self.assertIsNone(err)
        self.assertRegex(text, r"^Today=\d{4}-\d{2}-\d{2}$")

    def test_malicious_template_is_not_evaluated(self) -> None:
        secret = "TOP_SECRET_SHOULD_NOT_APPEAR"
        os.environ["AINOVEL_TEST_SECRET"] = secret
        template = "{{ cycler.__init__.__globals__.os.environ.AINOVEL_TEST_SECRET }}"
        text, _, err = render_template(template, {})
        self.assertIsNone(err)
        self.assertNotIn(secret, text)
        self.assertEqual(text, template)

        # Unsafe expressions inside control blocks must not be evaluated.
        template2 = "{% if cycler.__init__.__globals__.os.environ.AINOVEL_TEST_SECRET %}YES{% endif %}"
        text2, _, err2 = render_template(template2, {})
        self.assertIsNotNone(err2)
        self.assertNotIn(secret, text2)


if __name__ == "__main__":
    unittest.main()
