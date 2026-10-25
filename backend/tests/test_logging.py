"""验证日志关联、异常、输出过滤和中间件边界。"""

import asyncio
import io
import json
import logging
import re
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from starlette.responses import JSONResponse

from backend.app.api.exception_handlers import unhandled_exception_handler
from backend.app.api.middleware.request_logging import RequestLoggingMiddleware
from backend.app.core.logging import setup_logging
from backend.app.core.request_context import request_id_context


async def call_app(app, path="/probe"):
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"password=PRIVATE_QUERY",
        "root_path": "",
        "headers": [
            (b"authorization", b"Bearer PRIVATE_TOKEN"),
            (b"cookie", b"session=PRIVATE_COOKIE"),
            (b"x-request-id", b"untrusted-client-id"),
        ],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"PRIVATE_BODY", "more_body": False}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    return scope, messages


class LoggingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.stderr_patch = patch("sys.stderr", self.output)
        self.stderr_patch.start()
        setup_logging("DEBUG")

    def tearDown(self):
        self.stderr_patch.stop()
        setup_logging("INFO")

    async def test_concurrent_requests_keep_independent_context(self):
        logger = logging.getLogger("backend.tests.probe")

        async def endpoint(scope, receive, send):
            logger.info("处理前")
            await asyncio.sleep(0)
            logger.info("处理后")
            await JSONResponse({"request_id": request_id_context.get()})(scope, receive, send)

        app = RequestLoggingMiddleware(endpoint)
        results = await asyncio.gather(*(call_app(app, f"/probe/{index}") for index in range(12)))
        identifiers = []
        lines = self.output.getvalue().splitlines()
        for scope, messages in results:
            identifier = scope["state"]["request_id"]
            identifiers.append(identifier)
            self.assertRegex(identifier, r"^[a-f0-9]{32}$")
            response = next(message for message in messages if message["type"] == "http.response.start")
            self.assertEqual(dict(response["headers"])[b"x-request-id"].decode(), identifier)
            body = next(message["body"] for message in messages if message["type"] == "http.response.body")
            self.assertEqual(json.loads(body)["request_id"], identifier)
            correlated = [line for line in lines if f"request_id={identifier}" in line]
            self.assertEqual(len(correlated), 3)
            self.assertEqual(sum('message="请求完成"' in line for line in correlated), 1)
            self.assertTrue(any(f'path="{scope["path"]}"' in line for line in correlated))
        self.assertEqual(len(set(identifiers)), 12)
        self.assertEqual(request_id_context.get(), "-")
        for private in ("PRIVATE_QUERY", "PRIVATE_TOKEN", "PRIVATE_COOKIE", "PRIVATE_BODY", "untrusted-client-id"):
            self.assertNotIn(private, self.output.getvalue())

    async def test_unhandled_exception_has_one_stack_and_correlated_response(self):
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)
        app.add_exception_handler(Exception, unhandled_exception_handler)

        @app.get("/failure")
        async def failure():
            raise ValueError("probe failure")

        messages = []

        async def recording_app(scope, receive, send):
            async def record_send(message):
                messages.append(message)
                await send(message)
            await app(scope, receive, record_send)

        try:
            await call_app(recording_app, "/failure")
        except ValueError as exception:
            # 模拟 Uvicorn 再次记录 ASGI 异常，确认同一堆栈不会重复输出。
            logging.getLogger("uvicorn.error").error("Exception in ASGI application", exc_info=exception)
        else:
            self.fail("The middleware must preserve exception propagation")

        response = next(message for message in messages if message["type"] == "http.response.start")
        self.assertEqual(response["status"], 500)
        identifier = dict(response["headers"])[b"x-request-id"].decode()
        body = next(message["body"] for message in messages if message["type"] == "http.response.body")
        self.assertEqual(json.loads(body), {"detail": "Internal Server Error", "request_id": identifier})
        output = self.output.getvalue()
        self.assertIn(f"request_id={identifier}", output)
        self.assertIn("status_code=500", output)
        self.assertIn('exception_type="ValueError"', output)
        self.assertEqual(output.count("ValueError: probe failure"), 1)
        self.assertNotIn("Exception in ASGI application", output)
        self.assertEqual(request_id_context.get(), "-")

    async def test_expected_client_error_is_not_logged_as_exception(self):
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)
        _, messages = await call_app(app, "/missing")
        self.assertEqual(messages[0]["status"], 404)
        output = self.output.getvalue()
        self.assertIn(" INFO ", output)
        self.assertIn("status_code=404", output)
        self.assertNotIn("Traceback", output)

    def test_level_filtering_and_startup_context(self):
        setup_logging("WARNING")
        logger = logging.getLogger("backend.tests.level")
        logger.info("hidden_info")
        logger.warning("visible_warning")
        output = self.output.getvalue()
        self.assertNotIn("hidden_info", output)
        self.assertIn("visible_warning", output)
        self.assertIn("request_id=-", output)
        self.assertRegex(output, r"\d{4}-\d{2}-\d{2}T\S+[+-]\d{2}:\d{2} WARNING")

    def test_setup_is_repeatable_and_access_log_is_disabled(self):
        setup_logging("INFO")
        setup_logging("INFO")
        logging.getLogger("backend.tests.once").info("only_once")
        logging.getLogger("uvicorn.access").info("duplicate_access")
        self.assertEqual(self.output.getvalue().count("only_once"), 1)
        self.assertNotIn("duplicate_access", self.output.getvalue())

    def test_messages_cannot_inject_additional_log_lines(self):
        logging.getLogger("backend.tests.escape").info("first\nsecond")
        output = self.output.getvalue()
        self.assertEqual(len(output.splitlines()), 1)
        self.assertIn(r"first\nsecond", output)


if __name__ == "__main__":
    unittest.main()
