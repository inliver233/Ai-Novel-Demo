from __future__ import annotations

import logging
import unittest

from app.core import logging as logging_module


class TestLoggingSetup(unittest.TestCase):
    LOGGER_NAMES = (
        "ainovel",
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "fastapi",
        "httpx",
        "httpcore",
        "sqlalchemy",
        "py.warnings",
    )

    def setUp(self) -> None:
        root = logging.getLogger()
        self.root_handlers = list(root.handlers)
        self.root_level = root.level
        self.logger_states = {
            name: {
                "handlers": list(logging.getLogger(name).handlers),
                "level": logging.getLogger(name).level,
                "propagate": logging.getLogger(name).propagate,
            }
            for name in self.LOGGER_NAMES
        }

    def tearDown(self) -> None:
        root = logging.getLogger()
        root.handlers = self.root_handlers
        root.setLevel(self.root_level)
        for name, state in self.logger_states.items():
            current = logging.getLogger(name)
            current.handlers = state["handlers"]
            current.setLevel(state["level"])
            current.propagate = state["propagate"]

    def test_configure_logging_installs_intercept_handler(self) -> None:
        logging_module.configure_logging()

        root = logging.getLogger()
        self.assertEqual(len(root.handlers), 1)
        self.assertIsInstance(root.handlers[0], logging_module.InterceptHandler)
        self.assertTrue(logging.getLogger("uvicorn").propagate)
        self.assertEqual(logging.getLogger("uvicorn").handlers, [])
        self.assertEqual(logging.getLogger("httpx").level, logging.WARNING)
        self.assertEqual(logging.getLogger("httpcore").level, logging.WARNING)

    def test_configure_logging_is_idempotent(self) -> None:
        logging_module.configure_logging()
        logging_module.configure_logging()

        root = logging.getLogger()
        self.assertEqual(len(root.handlers), 1)
        self.assertIsInstance(root.handlers[0], logging_module.InterceptHandler)


if __name__ == "__main__":
    unittest.main()

