# 后端基础骨架

当前已实现 FastAPI 应用入口、健康检查、统一配置和请求日志。数据库连接、会话工具已独立实现，尚未接入请求生命周期。

## 启动

在项目根目录执行：

首次配置时，将 `.env.example` 复制为 `.env`，填写本机 MySQL 账号和密码；已有 `.env` 时直接修改，保留现有配置。

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
| `MYSQL_HOST` | 127.0.0.1 | MySQL 服务器地址，不能为空 |
| `MYSQL_PORT` | 3306 | MySQL 端口，整数且范围为 1～65535 |
| `MYSQL_DATABASE` | data_processing_platform | 项目数据库名，不能为空 |
| `MYSQL_USER` | 必填 | MySQL 连接账号，不能为空 |
| `MYSQL_PASSWORD` | 必填 | MySQL 连接密码，以 SecretStr 保存，不能为空 |

正常启动时，读取优先级为：环境变量 > `.env` > 代码默认值。

`APP_ENV` 目前仅用于标识环境，不会自动切换其他配置文件或修改调试模式。

`core/config.py` 根据文件自身位置定位项目根目录，不依赖启动时的工作目录。
配置通过类型与约束检查，空应用名、非法环境名、错误布尔值及 `.env` 中的未知配置项会报错。

`get_settings()` 在每个进程内缓存配置。修改 `.env` 或环境变量后，需要重启后端；不要依赖 `--reload` 自动监测 `.env`。

`.env` 已加入 Git 忽略规则，可提交 `.env.example` 供其他开发者参考。模板中的账号和密码留空；JWT 配置将在认证模块加入。

MySQL 配置负责读取与校验，数据库引擎和会话工具通过传入的配置或引擎创建，不在导入时自动连接数据库。
普通配置表示和 JSON 序列化会遮蔽密码；密码原始字符（包括前导零和前后空格）保持不变。
连接模块通过 `mysql_password.get_secret_value()` 取得密码，不应将此值写入日志。
配置校验错误的文本隐藏原始输入，不要自行记录包含完整输入的校验详情。

## 数据库连接与会话

- `infrastructure/db/connection.py` 的 `create_database_engine(settings)` 创建引擎和连接池，连接按需建立。
- `infrastructure/db/session.py` 的 `create_session_factory(engine)` 创建绑定到已有引擎的会话工厂，后续每次调用工厂会得到独立的 Session。
- `session_scope(factory)` 支持 `with` 语法，异常时回滚并继续抛出异常，结束时始终关闭会话、释放其占用资源。
- `session_scope` 不自动提交。业务层显式调用 `session.commit()`，或组织自己的事务边界；未提交事务在关闭会话时回滚。
- 每个请求或任务独立使用 Session；一个进程内复用引擎和会话工厂。应用组装与启动关闭接入将在后续实现。

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
