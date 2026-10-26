"""测试中直接发送 ASGI 请求，无需启动端口或额外 HTTP 客户端依赖。"""

import json


async def request_json(app, path, method="GET", payload=None, headers=None):
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8") if payload is not None else b""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
        + [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
        "state": {},
    }
    messages = []
    received = False

    async def receive():
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    try:
        await app(scope, receive, send)
    except Exception:
        # Starlette 在返回通用 500 后仍会重新抛出异常，允许测试断言该响应。
        if not any(message["type"] == "http.response.start" and message["status"] == 500 for message in messages):
            raise

    start = next(message for message in messages if message["type"] == "http.response.start")
    response = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return start["status"], json.loads(response)


async def post_json(app, payload):
    return await request_json(app, "/api/auth/register", "POST", payload)
