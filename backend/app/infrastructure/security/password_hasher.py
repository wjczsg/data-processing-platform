"""调用 argon2-cffi 生成 Argon2id 密码哈希并验证密码。"""

from argon2 import PasswordHasher as Argon2LibraryHasher
from argon2.exceptions import (
    HashingError,
    InvalidHashError,
    UnsupportedParametersError,
    VerificationError,
    VerifyMismatchError,
)
from argon2.low_level import Type

from backend.app.application.ports.password_hasher import PasswordHasher, PasswordHashError


class Argon2PasswordHasher(PasswordHasher):
    """密码处理接口的 Argon2 实现，新生成的哈希使用 Argon2id。"""

    def __init__(self) -> None:
        # 使用库的默认成本参数，明确指定 Argon2id，随机盐由库生成。
        self._hasher = Argon2LibraryHasher(type=Type.ID)

    def hash_password(self, password: str) -> str:
        """将已通过新密码规则校验的原始字符串转换为密码哈希。

        保留大小写及首尾空格，不访问数据库，不记录密码或哈希。
        返回值包含算法、成本参数、盐和哈希结果，可保存到 password_hash。
        """
        if not isinstance(password, str):
            raise PasswordHashError("密码必须是字符串")

        try:
            return self._hasher.hash(password)
        except (HashingError, UnicodeEncodeError, OSError) as error:
            # 向业务层提供稳定的异常类型，不让业务代码依赖 argon2 的异常。
            raise PasswordHashError("密码哈希生成失败") from error

    def verify_password(self, password: str, password_hash: str) -> bool:
        """使用已存哈希中的盐和参数验证密码，不修改输入或重新校验注册规则。"""
        if not isinstance(password, str) or not isinstance(password_hash, str):
            raise PasswordHashError("密码和密码哈希必须是字符串")

        try:
            # 项目接口先传密码，argon2-cffi 的 verify 则先接收已存哈希。
            return self._hasher.verify(password_hash, password)
        except VerifyMismatchError:
            # 密码不匹配是正常的验证结果，必须在 VerificationError 前处理。
            return False
        except (
            VerificationError,
            InvalidHashError,
            UnsupportedParametersError,
            UnicodeEncodeError,
            OSError,
        ) as error:
            # 哈希损坏或处理失败不能当作普通的密码错误，交给业务层处理。
            raise PasswordHashError("密码哈希验证失败") from error
