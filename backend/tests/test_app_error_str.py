from __future__ import annotations

import unittest

from app.core.errors import AppError


class TestAppErrorStr(unittest.TestCase):
    def test_str_returns_message(self) -> None:
        err = AppError(code="TEST", message="hello")
        self.assertEqual(str(err), "hello")
        self.assertEqual(err.args, ("hello",))

    def test_factory_methods_set_args(self) -> None:
        err = AppError.validation("bad input")
        self.assertEqual(str(err), "bad input")
        self.assertEqual(err.args, ("bad input",))

