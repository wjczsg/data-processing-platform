"""验证本地注册页面的跨域预检及失败响应头，不访问数据库。"""

import unittest

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.app.api.middleware.cors import configure_cors
from backend.app.core.config import Settings


class CORSTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = FastAPI()
        settings = Settings(_env_file=None, mysql_user="test", mysql_password="test-only")
        configure_cors(self.app, settings)

        @self.app.post("/probe")
        def conflict():
            return JSONResponse(status_code=409, content={"detail": "用户名已存在"})

    async def request(self, method, origin, requested_method="POST", requested_headers="content-type"):
        headers = [(b"origin", origin.encode())]
        if method == "OPTIONS":
            headers += [
                (b"access-control-request-method", requested_method.encode()),
                (b"access-control-request-headers", requested_headers.encode()),
            ]
        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": method, "scheme": "http", "path": "/probe", "raw_path": b"/probe",
            "query_string": b"", "root_path": "", "headers": headers,
            "client": ("127.0.0.1", 1234), "server": ("testserver", 80),
        }
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        await self.app(scope, receive, send)
        return next(message for message in messages if message["type"] == "http.response.start")

    async def test_both_local_frontend_origins_pass_preflight(self):
        for origin in ("http://127.0.0.1:8765", "http://localhost:8765"):
            with self.subTest(origin=origin):
                response = await self.request("OPTIONS", origin)
                headers = dict(response["headers"])
                self.assertEqual(response["status"], 200)
                self.assertEqual(headers[b"access-control-allow-origin"].decode(), origin)
                self.assertIn(b"POST", headers[b"access-control-allow-methods"])
                self.assertNotIn(b"access-control-allow-credentials", headers)

    async def test_unlisted_origin_fails_preflight(self):
        response = await self.request("OPTIONS", "http://localhost:3000")
        self.assertEqual(response["status"], 400)
        self.assertNotIn(b"access-control-allow-origin", dict(response["headers"]))

    async def test_browser_can_read_duplicate_account_response(self):
        response = await self.request("POST", "http://127.0.0.1:8765")
        self.assertEqual(response["status"], 409)
        self.assertEqual(dict(response["headers"])[b"access-control-allow-origin"], b"http://127.0.0.1:8765")

    async def test_bearer_header_is_allowed_for_current_user_request(self):
        response = await self.request("OPTIONS", "http://127.0.0.1:8765", "GET", "authorization")
        self.assertEqual(response["status"], 200)
        self.assertIn(b"GET", dict(response["headers"])[b"access-control-allow-methods"])


if __name__ == "__main__":
    unittest.main()
