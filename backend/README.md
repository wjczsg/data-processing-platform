# 后端基础骨架

当前已实现 FastAPI 应用入口、健康检查、统一配置和请求日志。

## 启动

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --port 8000
```

接口文档：http://127.0.0.1:8000/docs

健康检查：http://127.0.0.1:8000/api/health

## 配置

本机配置文件为项目根目录的 `.env`，示例为 `.env.example`。

| 配置项 | 默认值 | 用途 |
| --- | --- | --- |
| `APP_NAME` | 数据处理平台 | 应用及接口文档名称 |
| `APP_VERSION` | 0.1.0 | 接口文档中的版本 |
| `APP_ENV` | development | 标识运行环境，可选 development、test、production |
| `DEBUG` | false | FastAPI 调试模式 |
| `LOG_LEVEL` | INFO | 终端日志级别，可选 DEBUG、INFO、WARNING、ERROR、CRITICAL |

正常启动时，读取优先级为：环境变量 > `.env` > 代码默认值。

`APP_ENV` 目前仅用于标识环境，不会自动切换其他配置文件或修改调试模式。

`core/config.py` 根据文件自身位置定位项目根目录，不依赖启动时的工作目录。
配置通过类型与约束检查，空应用名、非法环境名、错误布尔值及 `.env` 中的未知配置项会报错。

`get_settings()` 在每个进程内缓存配置。修改 `.env` 或环境变量后，需要重启后端；不要依赖 `--reload` 自动监测 `.env`。

`.env` 已加入 Git 忽略规则，可提交 `.env.example` 供其他开发者参考。后续 MySQL 和 JWT 的配置将随对应模块加入。

## 日志

日志输出到终端，时间包含服务器本地时区。每个模块使用 `logging.getLogger(__name__)`，统一使用公共格式。

```text
2026-10-25T10:30:00.000+08:00 INFO backend.app.api.middleware.request_logging request_id=随机编号 method="GET" path="/api/health" status_code=200 duration_ms=2.4 message="请求完成"
```

- 公共字段：时间、级别、模块、消息；请求相关日志自动带 `request_id`，请求外为 `-`。
- 请求完成或失败事件补充 `method`、`path`、`status_code`、`duration_ms`。
- 服务端为每次请求生成新编号，不直接使用客户端传来的编号。正常响应的 `X-Request-ID` 头中也会返回该编号。
- 未处理异常以 ERROR 级别记录异常类型和堆栈，再交给框架处理；默认非调试模式下的 500 响应也带编号。
- Uvicorn 默认访问日志关闭，已记录的异常堆栈不重复输出。进程启动和退出日志保留。
- 不读取请求体、查询参数、Cookie、Authorization 或文件内容到请求日志。业务代码也不应自行记录密码、令牌等敏感值。
- 使用上下文变量关联并发请求，请求结束后清理上下文。
- 暂不写日志文件。修改 `LOG_LEVEL` 后重启服务。
