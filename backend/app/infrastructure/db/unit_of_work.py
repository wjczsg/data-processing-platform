"""以已有 SQLAlchemy Session 实现用户事务约定。"""

from sqlalchemy.orm import Session

from backend.app.application.ports.unit_of_work import UserUnitOfWork
from backend.app.application.ports.user_repository import UserRepository
from backend.app.infrastructure.repositories.user_repository import MySQLUserRepository
from backend.app.infrastructure.repositories.auth_sessions import MySQLAuthSessionRepository


class MySQLUserUnitOfWork(UserUnitOfWork):
    def __init__(self, session: Session) -> None:
        self._session = session
        self.users: UserRepository = MySQLUserRepository(session)
        self.auth_sessions = MySQLAuthSessionRepository(session)

    def commit(self) -> None:
        self._session.commit()
