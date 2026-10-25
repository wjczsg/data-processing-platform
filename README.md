# 数据处理平台

以下命令均在项目根目录（`requirements.txt` 所在目录）的 PowerShell 终端中执行。
使用项目已有的 `.venv`，无需先手动激活虚拟环境。

## 启动后端

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --port 8000
```

- 接口文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- 已提供 `POST /api/auth/register` 注册接口，可通过接口文档填写账号、密码和确认密码测试；成功后会真实写入 MySQL。
- 健康检查：[http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)
- 首次运行的依赖安装和 `.env` 配置见 [后端说明](backend/README.md)。

## 启动前端预览

如需同时运行前后端，请另开一个终端，在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m http.server 8765 --bind 127.0.0.1 --directory frontend
```

- 登录／注册页面：[http://127.0.0.1:8765/auth.html](http://127.0.0.1:8765/auth.html)
- 工作台：[http://127.0.0.1:8765/](http://127.0.0.1:8765/)
- 前端目前为页面原型，登录、注册提交尚未接入后端。

在对应终端按 `Ctrl+C` 停止服务。前端详细说明见 [前端说明](frontend/README.md)。
