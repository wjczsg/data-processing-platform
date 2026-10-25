"""使用 SQLAlchemy Session 访问 MySQL 的 users 表。"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.application.ports.user_repository import (
    UserRepository,
    UsernameAlreadyExistsError,
)
from backend.app.domain.user import User, UserRole, normalize_username
from backend.app.infrastructure.db.models.user import UserModel


class MySQLUserRepository(UserRepository):
    def __init__(self, session: Session) -> None:
        # 会话由调用方提供，同一业务事务可以复用这个会话。
        self._session = session

    def get_by_id(self, user_id: int) -> User | None:
        model = self._session.get(UserModel, user_id)
        return self._to_user(model) if model is not None else None

    def get_by_username(self, username: str) -> User | None:
        normalized = normalize_username(username)
        statement = select(UserModel).where(UserModel.username == normalized)
        model = self._session.scalar(statement)
        return self._to_user(model) if model is not None else None

    def add(self, user: User) -> User:
        if user.id is not None:
            raise ValueError("新增用户不能携带已有 ID")

        model = UserModel(
            username=user.username,
            password_hash=user.password_hash,
            role=user.role.value,
            is_active=user.is_active,
        )
        self._session.add(model)
        try:
            # 取得自增 ID 和 ORM 生成的时间，同时触发数据库唯一性约束。
            # flush 不等于 commit；最终提交仍由调用方决定。
            self._session.flush()
        except IntegrityError as error:
            # 仅翻译 MySQL 的用户名唯一索引冲突，其余数据库错误原样抛出。
            driver_args = getattr(error.orig, "args", ())
            if (
                len(driver_args) >= 2
                and driver_args[0] == 1062
                and "uq_users_username" in str(driver_args[1])
            ):
                raise UsernameAlreadyExistsError("用户名已存在") from error
            raise

        return self._to_user(model)

    @staticmethod
    def _to_user(model: UserModel) -> User:
        """将 ORM 对象转换成独立数据，关闭会话后仍能读取字段。"""
        return User(
            id=model.id,
            username=model.username,
            password_hash=model.password_hash,
            role=UserRole(model.role),
            is_active=model.is_active,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
