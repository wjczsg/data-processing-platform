"""上传文件的业务规则，不依赖 HTTP、数据库或具体存储方式。"""

from pathlib import PurePath


class FileTooLargeError(ValueError):
    """实际文件内容大小超过允许的上限。"""


class EmptyFileError(ValueError):
    """实际文件内容为零字节。"""


class InvalidFileEncodingError(ValueError):
    """文件字节无法按要求的 UTF-8 编码完整解码。"""


class InvalidCsvFormatError(ValueError):
    """CSV 解析失败，行号表示已读取到的物理行位置。"""

    def __init__(self, line_number: int) -> None:
        self.line_number = line_number
        super().__init__(f"CSV 格式错误，解析在第 {line_number} 个物理行附近失败")


def validate_csv_filename(filename: str | None) -> None:
    """只允许 .csv 扩展名，忽略大小写；文件内容合法性由后续解析确认。"""
    if not filename or PurePath(filename).suffix.lower() != ".csv":
        raise ValueError("仅支持上传 CSV 文件（.csv）")


def validate_file_size(size_bytes: int, max_bytes: int) -> None:
    """小于或等于上限均允许；仅检查上限，不判断空文件。"""
    if size_bytes > max_bytes:
        if max_bytes % (1024 * 1024) == 0:
            limit = f"{max_bytes // (1024 * 1024)} MiB"
        else:
            limit = f"{max_bytes} 字节"
        raise FileTooLargeError(f"文件大小不能超过 {limit}")


def validate_non_empty_file(size_bytes: int) -> None:
    """读取结束后拒绝零字节文件；有字节不代表存在有效 CSV 数据。"""
    if size_bytes == 0:
        raise EmptyFileError("不能上传空文件")
