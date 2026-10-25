"""复用项目配置与模型，支持迁移生成、在线执行和离线 SQL 预览。"""

import logging

from alembic import context

from backend.app.core.config import get_settings
from backend.app.core.logging import setup_logging
from backend.app.infrastructure.db.connection import create_database_engine
from backend.app.infrastructure.db.models import Base

# models 包已导入所有已声明模型，元数据包含 users 表。
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """只生成 MySQL SQL 文本，不连接数据库，也不需要读取密码。"""
    setup_logging("INFO")
    context.configure(
        dialect_name="mysql",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """连接目标数据库进行结构对比或执行明确指定的迁移命令。"""
    settings = get_settings()
    setup_logging(settings.log_level)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            migration_context = context.get_context()
            if migration_context.opts.get("revision_context") is not None:
                # 生成脚本时不自动创建 alembic_version；实际 upgrade 时再创建。
                migration_context.opts["dont_mutate"] = True
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
