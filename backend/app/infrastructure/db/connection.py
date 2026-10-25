"""根据传入配置创建数据库引擎。"""

from sqlalchemy import Engine, URL, create_engine

from backend.app.core.config import Settings


def create_database_engine(settings: Settings) -> Engine:
    """创建 MySQL 引擎；实际连接在取用时按需建立。"""
    database_url = URL.create(
        drivername="mysql+pymysql",
        username=settings.mysql_user,
        password=settings.mysql_password.get_secret_value(),
        host=settings.mysql_host,
        port=settings.mysql_port,
        database=settings.mysql_database,
        query={"charset": "utf8mb4"},
    )

    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=10,
        connect_args={"connect_timeout": 5},
        hide_parameters=True,
        echo=False,
    )
