import unittest

from starlette.requests import Request
from starlette.responses import Response

from app.core.request_id import get_request_id
from app.main import request_id_and_logging_middleware


async def _receive() -> dict:
    return {"type": "http.request", "body": b"", "more_body": False}


def _make_request(rid: str) -> Request:
    scope = {
        "type": "http",
        "asgi": {"spec_version": "2.1", "version": "3.0"},
        "http_version": "1.1",
        "scheme": "http",
        "method": "GET",
        "path": "/test",
        "raw_path": b"/test",
        "query_string": b"",
        "headers": [(b"x-request-id", rid.encode("ascii"))],
        "client": ("testclient", 123),
        "server": ("testserver", 80),
    }
    return Request(scope, _receive)


class TestRequestIdContextReset(unittest.IsolatedAsyncioTestCase):
    async def test_request_id_context_is_reset_after_request(self) -> None:
        self.assertIsNone(get_request_id())

        async def call_next(_request: Request) -> Response:
            self.assertEqual(get_request_id(), "rid-1")
            return Response("ok", status_code=200)

        response = await request_id_and_logging_middleware(_make_request("rid-1"), call_next)
        self.assertEqual(response.headers.get("X-Request-Id"), "rid-1")
        self.assertIsNone(get_request_id())

        async def call_next_2(_request: Request) -> Response:
            self.assertEqual(get_request_id(), "rid-2")
            return Response("ok", status_code=200)

        response_2 = await request_id_and_logging_middleware(_make_request("rid-2"), call_next_2)
        self.assertEqual(response_2.headers.get("X-Request-Id"), "rid-2")
        self.assertIsNone(get_request_id())


if __name__ == "__main__":
    unittest.main()

