"""本地开发入口：同时启动前端静态页面和可自动重载的后端。"""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parent


def main() -> None:
    handler = partial(SimpleHTTPRequestHandler, directory=str(PROJECT_ROOT / "frontend"))
    try:
        frontend = ThreadingHTTPServer(("127.0.0.1", 8765), handler)
    except OSError as error:
        raise SystemExit(f"前端启动失败：{error}。如果 8765 端口已被占用，请先停止旧的前端服务。") from None

    thread = Thread(target=frontend.serve_forever, name="frontend-server", daemon=True)
    thread.start()
    print("前端账号页面：http://127.0.0.1:8765/auth.html", flush=True)
    print("后端接口文档：http://127.0.0.1:8000/docs", flush=True)
    print("按 Ctrl+C 同时停止前后端。", flush=True)

    try:
        uvicorn.run(
            "backend.app.main:app",
            host="127.0.0.1",
            port=8000,
            reload=True,
            reload_dirs=[str(PROJECT_ROOT / "backend")],
            app_dir=str(PROJECT_ROOT),
        )
    except KeyboardInterrupt:
        pass
    finally:
        frontend.shutdown()
        frontend.server_close()
        thread.join()


if __name__ == "__main__":
    main()
