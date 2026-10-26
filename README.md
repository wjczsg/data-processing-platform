# 数据处理平台

以下命令均在项目根目录（`requirements.txt` 所在目录）的 PowerShell 终端中执行。
使用项目已有的 `.venv`，无需先手动激活虚拟环境。

## 一条命令启动前后端（推荐）

```powershell
.\.venv\Scripts\python.exe dev.py
```

该命令在同一个终端启动前端 `8765` 和后端 `8000`：

- 账号页面：[http://127.0.0.1:8765/auth.html](http://127.0.0.1:8765/auth.html)
- 工作台：[http://127.0.0.1:8765/](http://127.0.0.1:8765/)
- 接口文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

按一次 `Ctrl+C` 同时停止前后端。修改后端 Python 代码会自动重载；修改前端后刷新页面即可。
如果原来已分别启动服务，先在旧终端按 `Ctrl+C` 停止，避免端口占用。
此脚本用于本地开发，MySQL 服务仍需提前运行。首次运行的依赖及 `.env` 配置见 [后端说明](backend/README.md)。

## 单独启动后端

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --port 8000
```

- 接口文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- 已提供 `POST /api/auth/register`、`POST /api/auth/login` 和受保护的 `GET /api/auth/me`，可通过接口文档测试。
- 健康检查：[http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)
- 首次运行的依赖安装和 `.env` 配置见 [后端说明](backend/README.md)。

## 单独启动前端预览

如需同时运行前后端，请另开一个终端，在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m http.server 8765 --bind 127.0.0.1 --directory frontend
```

- 登录／注册页面：[http://127.0.0.1:8765/auth.html](http://127.0.0.1:8765/auth.html)
- 工作台：[http://127.0.0.1:8765/](http://127.0.0.1:8765/)
- 注册、登录按钮均已接入后端；登录成功进入工作台并显示当前账号，可以退出登录。工作台文件和任务仍为静态示例。
- 登录代码逐块说明见 [登录实现说明](backend/LOGIN_FLOW.md)。令牌默认 30 分钟有效，只保存在当前标签页；普通工作台入口会先向后端确认身份。
- 使用页面注册时，需要同时运行前端 `8765` 和后端 `8000`；修改后刷新页面即可，旧页面可按 `Ctrl+F5` 强制刷新。

在对应终端按 `Ctrl+C` 停止服务。前端详细说明见 [前端说明](frontend/README.md)。
