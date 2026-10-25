# 后端基础骨架

当前已实现 FastAPI 应用入口、健康检查和统一配置管理。

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

正常启动时，读取优先级为：环境变量 > `.env` > 代码默认值。

`APP_ENV` 目前仅用于标识环境，不会自动切换其他配置文件或修改调试模式。

`core/config.py` 根据文件自身位置定位项目根目录，不依赖启动时的工作目录。
配置通过类型与约束检查，空应用名、非法环境名、错误布尔值及 `.env` 中的未知配置项会报错。

`get_settings()` 在每个进程内缓存配置。修改 `.env` 或环境变量后，需要重启后端；不要依赖 `--reload` 自动监测 `.env`。

`.env` 已加入 Git 忽略规则，可提交 `.env.example` 供其他开发者参考。后续 MySQL 和 JWT 的配置将随对应模块加入。
