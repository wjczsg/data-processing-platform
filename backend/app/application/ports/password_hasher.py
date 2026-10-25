"""密码哈希与验证的调用约定，不依赖具体哈希库或数据库。"""

from typing import Protocol


class PasswordHashError(Exception):
    """无法完成哈希处理，例如生成失败或已存哈希损坏；不表示密码不匹配。"""


class PasswordHasher(Protocol):
    """注册、登录业务依赖的密码处理接口。

    实现类保留密码的大小写和首尾空格，不记录密码或哈希。
    新密码规则由调用方使用 validate_new_password() 单独校验。
    """

    def hash_password(self, password: str) -> str:
        """生成包含算法参数及随机盐的哈希字符串，供调用方保存。

        每次生成使用独立随机盐，不修改输入密码，不访问数据库。
        无法生成哈希时抛出 PasswordHashError。
        """
        ...

    def verify_password(self, password: str, password_hash: str) -> bool:
        """验证输入密码与已存哈希：匹配返回 True，不匹配返回 False。

        不重新执行注册时的新密码规则，也不通过重新生成哈希后比较字符串。
        已存哈希损坏、格式不支持或验证处理失败时抛出 PasswordHashError，
        实现类不将底层哈希库的异常直接暴露给业务层。
        """
        ...
