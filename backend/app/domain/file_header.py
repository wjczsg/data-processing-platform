"""表头确认结果和列名规则，不依赖 HTTP、数据库或文件系统。"""

from dataclasses import dataclass


class InvalidFileHeaderError(ValueError):
    """文件无法按用户选择形成可用列信息。"""


@dataclass(frozen=True)
class FileColumn:
    index: int
    name: str


@dataclass(frozen=True)
class FileHeaderConfiguration:
    file_id: str
    has_header: bool
    columns: tuple[FileColumn, ...]


def build_file_columns(record: list[str], has_header: bool) -> tuple[FileColumn, ...]:
    if not record:
        raise InvalidFileHeaderError("文件中没有可用于确定列信息的记录")
    if not has_header:
        return tuple(FileColumn(index, f"column_{index + 1}") for index in range(len(record)))
    columns = []
    seen = set()
    for index, value in enumerate(record):
        name = value.strip()
        if not name:
            raise InvalidFileHeaderError(f"第 {index + 1} 列的列名不能为空")
        if name in seen:
            # 不回显可能很长的文件字段，响应大小不随上传内容膨胀。
            raise InvalidFileHeaderError(f"第 {index + 1} 列的列名与前面的列名重复")
        seen.add(name)
        columns.append(FileColumn(index, name))
    return tuple(columns)
