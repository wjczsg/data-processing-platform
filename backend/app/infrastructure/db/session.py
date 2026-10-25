"""创建数据库会话，并管理会话的释放与异常回滚。"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """工厂绑定已有引擎，每次调用工厂都会得到独立的 Session。"""
    return sessionmaker(bind=engine)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """提供会话，异常时回滚，结束时关闭；写入需业务层显式提交。"""
    session = session_factory()

    try:
        yield session
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
