# 后端基础骨架

当前已实现 FastAPI 应用入口、健康检查、统一配置、请求日志和用户注册接口。数据库连接池、会话和密码哈希能力已接入应用生命周期，注册请求使用独立事务。

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
| `CORS_ALLOWED_ORIGINS` | 本地 `127.0.0.1:8765`、`localhost:8765` | 允许浏览器访问的前端来源，环境变量使用 JSON 数组，修改后重启后端 |
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
- 每个注册请求独立使用 Session；一个进程内复用引擎、会话工厂和密码哈希工具。应用启动时创建这些资源，关闭时释放连接池；真实数据库连接仍按需建立。
- `infrastructure/db/unit_of_work.py` 使用同一会话组装用户仓储和提交操作，实现 `application/ports/unit_of_work.py` 的事务接口，应用业务不依赖 SQLAlchemy。

## 用户数据与数据库模型

- `domain/user.py` 定义业务用户数据 `User`、角色 `UserRole` 和账号规范，不依赖 SQLAlchemy。
- `infrastructure/db/models/base.py` 定义统一 ORM 基类和约束命名规则。
- `infrastructure/db/models/user.py` 定义 `UserModel`，描述 MySQL `users` 表。
- `models/__init__.py` 集中导入模型，便于 Alembic 在下一阶段读取元数据。

用户表包含 `id`、`username`、`password_hash`、`role`、`is_active`、`created_at`、`updated_at`。
账号清理首尾空格、统一小写，限制为 3～32 位 ASCII 字母、数字或下划线。
定义账号唯一约束及字段检查约束；角色只允许 `user` 和 `admin`，默认普通用户，启用状态默认 true。
密码字段保存哈希，本阶段只检查非空和长度，哈希算法及密码验证在认证模块中实现。

ORM 中的时间使用 UTC，MySQL 以不带时区的 `DATETIME(6)` 保存。
时间默认值及 `updated_at` 更新函数由 SQLAlchemy 写入时执行，直接使用 SQL 写入时需要显式提供或维护时间。
业务层 `User` 是只读数据结构，尚未保存时 ID 和时间为空，密码哈希不包含在默认 repr 中；不能直接把包含哈希的对象作为接口响应。

本地数据库 `data_processing_platform` 已应用首个迁移 `0001`，`users` 表已创建，账号唯一性等数据库约束已生效。

## 用户数据访问

- `application/ports/user_repository.py` 使用 `Protocol` 定义 `UserRepository`，约定 `get_by_id()`、`get_by_username()` 和 `add()`，不依赖 SQLAlchemy。
- `infrastructure/repositories/user_repository.py` 中的 `MySQLUserRepository` 接收外部 Session，执行 SQLAlchemy 查询和写入，并返回业务层 `User`。
- 查询不到用户返回 `None`。按用户名查询会先清理空格、统一小写，格式非法抛出 `ValueError`。
- `add()` 只接收 ID 为空的新用户；密码哈希需预先生成。调用 `flush()` 后返回带 ID 和时间的新对象，不修改原来的只读对象。
- 用户名唯一约束冲突转换为 `UsernameAlreadyExistsError`，其他数据库异常继续抛出。数据库约束负责阻止并发重复写入，注册前的查询不能代替此约束。
- 数据访问层不提交、回滚或关闭会话。调用方组织事务，成功后显式 `commit()`，异常由现有 `session_scope()` 回滚并释放连接。
- 用户数据访问已接入注册 HTTP 接口和前端注册按钮；登录接口尚未接入。

真实 MySQL 集成测试需先应用迁移，再在项目根目录显式开启：

```powershell
$env:RUN_MYSQL_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest backend.tests.test_user_repository_mysql -v
Remove-Item Env:RUN_MYSQL_TESTS
```

测试检查新增、查询、用户名规范化、冲突处理及事务隔离，测试数据全部回滚，不留下用户记录；MySQL 自增 ID 计数可能前进，这是正常行为。

## 新密码规则

`domain/password.py` 提供独立于数据库和哈希算法的规则函数：

- `validate_new_password(password)` 用于注册、修改密码：8～128 个 Unicode 码点，支持中文、符号和普通空格，不强制字符组合。
- 拒绝全空白、控制字符、换行分隔符、无效 Unicode 代理码点及本地名单中的常见弱密码。当前名单为基础名单，不等同于完整泄露密码库。
- 不清理密码首尾空格、不改变大小写；仅在弱密码名单匹配时忽略大小写。
- `validate_password_confirmation(password, confirmation)` 独立检查两次输入完全一致。
- 校验成功返回 `None`，失败抛出不包含密码原文的 `ValueError`。
- 明文密码规则与 `User.password_hash` 的哈希字段规则分开；登录不重新套用新密码规则。

前端注册页显示相同长度要求，并提供长度、确认密码的本地输入提示；后端函数在注册业务中执行完整规则校验。
已安装密码哈希库 `argon2-cffi==25.1.0`，其 `PasswordHasher` 默认使用 Argon2id；依赖记录在根目录 `requirements.txt`。
哈希生成、密码验证和注册 HTTP 接口已实现；登录 HTTP 接口尚未实现。

规则测试：`.\.venv\Scripts\python.exe -m unittest backend.tests.test_password_policy -v`。

## 密码处理接口

`application/ports/password_hasher.py` 使用 `Protocol` 定义 `PasswordHasher`，不依赖 `argon2-cffi` 或数据库：

- `hash_password(password) -> str`：生成包含算法参数和随机盐的哈希，供注册业务保存。
- `verify_password(password, password_hash) -> bool`：验证密码，匹配返回 `True`，不匹配返回 `False`。
- `PasswordHashError`：约定生成失败、已存哈希损坏等处理异常，与正常的密码不匹配分开；具体实现负责翻译底层库异常。
- 接口只定义调用约定，Argon2id 具体实现位于 `infrastructure/security/password_hasher.py`。
- 注册流程先调用 `validate_new_password()`，再生成哈希；登录验证不重新套用新密码规则。接口不负责数据库读写或签发令牌。

`Argon2PasswordHasher` 已实现并继承 `PasswordHasher` 接口，提供 `hash_password()` 和 `verify_password()`。
生成时明确使用 Argon2id，采用库默认成本参数和自动随机盐，保留原始密码；失败转换为 `PasswordHashError`。
验证时由库读取已存哈希中的盐和参数；密码不匹配返回 `False`，哈希无效或验证过程失败抛出 `PasswordHashError`。
两个方法均不重复执行新密码规则、不直接写入数据库；注册业务已调用生成方法并接入前端提交。登录验证不改变密码的大小写或空格。

当前可单独调用生成哈希和验证密码：

```python
from backend.app.domain.password import validate_new_password
from backend.app.infrastructure.security.password_hasher import Argon2PasswordHasher

validate_new_password(password)
hasher = Argon2PasswordHasher()
password_hash = hasher.hash_password(password)
matches = hasher.verify_password(password, password_hash)
```

示例中的 `password` 由调用方提供；不要将密码或生成的哈希写入日志。
生成与验证测试：`.\.venv\Scripts\python.exe -m unittest backend.tests.test_password_hashing -v`。

## 注册接口

`POST /api/auth/register` 接收 JSON：

```json
{
  "username": "student_01",
  "password": "LearnPython2026!",
  "password_confirmation": "LearnPython2026!"
}
```

启动后端后，可在 [接口文档](http://127.0.0.1:8000/docs) 展开注册接口，点击 Try it out、填写请求并 Execute。成功注册会在本机 MySQL 中保存真实用户。

- `api/schemas/auth.py` 定义请求、响应模型。密码使用 `SecretStr`，不清理空格；拒绝请求中的角色、启用状态等额外字段。
- `api/auth.py` 负责 HTTP 收发及状态码转换；`api/dependencies.py` 为每个请求提供事务及业务依赖。
- `application/register_user.py` 组织规则校验、账号规范化、重复检查、生成哈希、新增用户、提交事务，默认角色 `user`、启用状态 `true`。
- 数据库唯一约束负责阻止并发重复账号。异常时，原有 `session_scope()` 回滚并关闭会话，避免未完成的注册留下记录。
- `201`：注册成功，返回 `id`、`username`、`role`、`is_active`、`created_at`、`updated_at`，时间包含 UTC 标记。
- `409`：账号已存在。`422`：字段或密码规则不符合要求。`500`：未预期的内部处理失败，响应不暴露数据库或哈希异常细节。
- 请求校验错误统一只返回错误位置、描述和类型，移除默认错误详情中的原始输入，避免回显明文密码。
- 注册成功不会自动登录或签发令牌。前端注册按钮已接入，成功后切回登录表单；登录提交仍未开放。
- `api/middleware/cors.py` 使用配置中的来源名单，允许注册所需的 `POST` 和 `Content-Type` 跨域请求，不启用 Cookie 凭据。默认支持两个本地 `8765` 来源，其他来源预检被拒绝。

接口规则测试：`.\.venv\Scripts\python.exe -m unittest backend.tests.test_registration -v`。

真实 MySQL 注册检查（会真正提交临时账号，完成后只删除本次创建的唯一测试账号）：

```powershell
$env:RUN_MYSQL_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest backend.tests.test_registration_mysql -v
Remove-Item Env:RUN_MYSQL_TESTS
```

覆盖请求到数据库的实际提交、并发唯一性、提交失败时回滚及连接释放，不会清空用户表。自增 ID 计数可能前进。

## 数据库迁移

- 根目录 `alembic.ini` 指向 `backend/migrations`，不包含数据库密码或连接 URL。
- `backend/migrations/env.py` 在线时读取项目配置并复用数据库引擎，通过 `Base.metadata` 发现模型。
- 首个版本 `0001_create_users_table.py` 的 `upgrade()` 创建用户表，`downgrade()` 删除该表及其数据。
- 生成迁移时不自动创建版本跟踪表；真正执行升级时才创建并更新 `alembic_version`。

在项目根目录查看已有版本：

```powershell
.\.venv\Scripts\python.exe -m alembic history
```

离线预览 SQL（只输出文本，不连接或修改数据库）：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head --sql
```

应用迁移可执行 `.\.venv\Scripts\python.exe -m alembic upgrade head`。本地已执行 `upgrade 0001`，并通过 `alembic check` 确认数据库结构与当前模型一致。
首次应用会创建 `users` 和 `alembic_version`，不会自动插入用户。
MySQL DDL 不能按普通数据事务期待自动回滚；执行结构降级前需检查是否删除表或字段。
自动生成的脚本必须审查，字段改名、数据转换和已有 CHECK 约束变更尤其需要手动核对。

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
