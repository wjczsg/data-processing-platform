"""注册、修改密码时使用的明文密码规则，不依赖数据库或哈希库。"""

import unicodedata

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128

# 第一版本地常见弱密码名单；不是完整的泄露密码库。
# 仅在名单匹配时忽略大小写，实际密码始终保留原样。
COMMON_PASSWORDS = frozenset({
    "12345678",
    "123456789",
    "1234567890",
    "123456789012345",
    "password",
    "password1",
    "password123",
    "passwordpassword",
    "qwerty123",
    "qwertyuiop",
    "abc123456",
    "admin123",
    "administrator",
    "iloveyou",
    "letmein123",
    "welcome1",
})


def validate_new_password(password: str) -> None:
    """校验新密码；通过时返回 None，不修改、记录或存储原始输入。

    仅用于注册和修改密码，登录时由后续密码哈希模块验证已有凭据。
    长度按 Unicode 码点计算（Python len），不按 UTF-8 字节计算。
    """
    if not isinstance(password, str):
        raise ValueError("密码必须是字符串")
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        raise ValueError(f"密码长度必须为 {PASSWORD_MIN_LENGTH}～{PASSWORD_MAX_LENGTH} 个字符")
    if not password.strip():
        raise ValueError("密码不能全部为空白字符")
    if any(unicodedata.category(char) in {"Cc", "Cs", "Zl", "Zp"} for char in password):
        raise ValueError("密码不能包含换行、控制字符或无效 Unicode 字符")
    if password.casefold() in COMMON_PASSWORDS:
        raise ValueError("密码过于常见，请换一个密码")


def validate_password_confirmation(password: str, confirmation: str) -> None:
    """注册时检查两次输入完全一致，区分大小写并保留首尾空格。"""
    if not isinstance(password, str) or not isinstance(confirmation, str):
        raise ValueError("密码和确认密码必须是字符串")
    if password != confirmation:
        raise ValueError("两次输入的密码不一致")
