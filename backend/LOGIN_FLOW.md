# 登录功能：逐块阅读

完整流程：账号密码 → 登录请求模型 → 登录业务 → 查询用户和验证密码 → 签发 JWT → 前端保存令牌 → 携带令牌查询当前用户 → 显示工作台。

## 1. 配置：core/config.py

- `jwt_secret_key`：服务器签名、验签用的秘密，使用 `SecretStr` 隐藏显示。至少 32 字符，真实值只保存在本机忽略的 `.env` 或环境变量中。
- `jwt_access_token_expire_minutes`：访问令牌有效期，默认 30 分钟。
- 密钥在重启后保持不变；修改密钥会使旧令牌失效。应用启动时检查密钥是否已经配置。

首次克隆项目时，可自行生成密钥并填写 `.env`：

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

生成值填入 `JWT_SECRET_KEY`，不要提交到 Git。当前电脑已自动生成并保存，不需要重复生成。

## 2. 接口约定：application/ports/token_service.py

- `AccessToken`：保存令牌字符串和剩余有效秒数，默认对象显示不包含令牌值。
- `TokenService.issue_access_token(user_id)`：约定如何签发令牌。
- `TokenService.verify_access_token(token)`：约定验证后返回用户 ID。
- `InvalidAccessTokenError`：表示令牌无效、已过期，或关联用户不可用。

这里和用户仓储、密码处理的 Protocol 一样，只规定调用方式，业务不直接依赖 PyJWT。

## 3. JWT 实现：infrastructure/security/token_service.py

`__init__()` 接收密钥和有效期；它不会查询数据库。

`issue_access_token()` 生成这些字段：

| 字段 | 含义 |
| --- | --- |
| `sub` | 用户 ID，使用字符串 |
| `iat` | 签发时间 |
| `exp` | 到期时间 |
| `iss` / `aud` | 签发方 / 接收方，用于区分令牌用途 |
| `token_type` | 当前为 `access` |

随后用固定的 HS256 算法签名。令牌中不放密码或密码哈希；JWT 签名用于校验是否被修改，不是对载荷进行加密。

`verify_access_token()` 使用服务器指定的算法和密钥检查签名，并检查有效期、签发方、接收方、必要字段及用户 ID。通过后才返回 ID；失败转成统一的应用异常。算法固定的做法参考 [PyJWT 官方说明](https://pyjwt.readthedocs.io/en/stable/api.html#jwt.decode)。

## 4. 登录业务：application/authenticate_user.py

`AuthenticationService.__init__()` 接收四个依赖：用户仓储、密码处理接口、令牌接口、备用密码哈希。

`login()` 的代码从上到下执行：

1. 规范化用户名，检查密码能否作为 UTF-8 输入。
2. 查询数据库中的用户。
3. 调用已有的 `verify_password()`。
4. 账号不存在时，仍用备用哈希完成一次验证，减少通过耗时判断账号是否存在的机会。
5. 账号不存在、密码错误、账号停用，均抛出同一种异常，对外提示“账号或密码错误”。
6. 校验通过后，用数据库用户 ID 签发令牌，返回 `LoginResult`。

登录不重新执行注册时的弱密码和最小长度规则；也不会新增用户或提交写事务。

`current_user()` 先验证令牌得到 ID，再查询最新数据库记录。用户被删除或停用后，已有令牌也无法通过这个接口。

## 5. HTTP 模型和路由：api/schemas/auth.py、api/auth.py

- `LoginRequest`：接收 JSON 账号、密码，密码不清理空格；拒绝额外字段。
- `LoginResponse`：返回访问令牌、令牌类型、有效秒数和公开用户信息。
- `POST /api/auth/login`：调用登录业务，成功返回 `200`，账号验证失败返回 `401`。
- 登录成功响应带 `Cache-Control: no-store`，避免缓存包含令牌的响应。
- `GET /api/auth/me`：从 `Authorization: Bearer <令牌>` 读取令牌，验证后返回当前用户。
- 缺少令牌、令牌过期或用户不可用时，`/me` 返回 `401`，不返回任何其他用户信息。
- `HTTPBearer` 让 FastAPI 从请求头提取令牌，同时让接口文档提供 Authorize 按钮。

## 6. 依赖组装：api/dependencies.py、app/main.py

应用启动时创建密码工具、JWT 工具及备用密码哈希，避免每个请求重复创建这些资源。

`get_authentication_service()` 为业务组装仓储、密码工具、令牌工具；用户仓储仍使用每个请求独立的数据库会话。

跨域配置允许本地前端发送 `GET`、`POST` 和 `Authorization` 请求头，不使用 Cookie 登录凭据。

## 7. 前端提交：frontend/auth.js

同一表单根据当前标签发送注册或登录请求：

- 注册：发送账号、密码、确认密码；成功切换到登录表单。
- 登录：只发送账号、密码；成功将访问令牌交给 `AuthSession`，清空密码，再进入 `index.html`。
- 请求期间禁用按钮和切换操作，防止重复提交；失败展示后端原因，并恢复操作。

## 8. 前端状态：frontend/auth-session.js

- `setToken()`：只将 JWT 放入当前标签页的 `sessionStorage`，不保存密码。
- `getToken()` / `clear()`：读取或清除当前标签页的令牌。
- `currentUser()`：携带 Bearer 请求头访问 `/api/auth/me`；收到 `401` 时清除令牌。

刷新页面时令牌仍在当前标签页；关闭标签页后会话存储清除。令牌只有通过后端验证后才代表有效登录。

## 9. 工作台入口：frontend/workbench-auth.js

- 普通入口：没有令牌时回到登录页面；有令牌则先向后端查询身份，成功后显示账号和退出按钮。
- 首次身份确认前隐藏工作台；网络失败或超时保留令牌，并以 2、5、10、30 秒退避自动重试。离线时等待浏览器的网络恢复事件，不把未知状态当作已登录。
- 网络恢复、页面重新可见时会再查身份；手动重试不刷新页面，已打开工作台的输入和界面状态保留。
- 登录失效：后端返回 `401` 时清理令牌、停止自动重试，在原页面提供重新登录入口，不强制跳转清空内容。
- 退出：清除当前标签页令牌并回到登录页。当前退出不会撤销已经签发的 JWT，它最多继续有效到到期；暂未实现刷新令牌、服务端撤销和失败尝试限流。
- `?preview=1` 是明确的静态示例预览，只显示演示数据，不绕过后端接口认证。

工作台文件、任务仍为静态示例。后续真实业务必须在数据库查询中增加当前用户归属条件；当前登录功能不等于已经完成所有业务数据隔离。

当前完成的是请求异常恢复，不包含自动签发新令牌。自动重试只用于只读的当前用户查询，避免重复提交注册、登录或未来的上传任务。

## 10. 检查入口

```powershell
.\.venv\Scripts\python.exe dev.py
```

打开 `http://127.0.0.1:8765/auth.html`，使用已注册的真实账号密码登录。接口文档的登录接口返回令牌后，可点击 Authorize，再测试 `/api/auth/me`。

自动检查覆盖正确/错误密码、缺少/过期/签名不符的令牌、必要声明、两个用户的身份、账号停用、密码原样处理，以及注册流程回归。真实 MySQL 检查只清理自己创建的临时账号。
