"""按固定规则校验完整 CSV，并返回有界的原始记录预览。"""

import csv
import io
from dataclasses import dataclass
from typing import BinaryIO

from backend.app.domain.file_rules import InvalidCsvFormatError, InvalidFileEncodingError
from backend.app.domain.file_header import FileColumn, InvalidFileHeaderError, build_file_columns

# 标准库默认只允许 128 KiB 单字段，会误拒当前上传上限内的长字段。
# 进程加载时统一放宽，不在并发请求中修改全局配置；文件总大小由上传接口限制。
csv.field_size_limit(max(csv.field_size_limit(), 2**31 - 1))

PREVIEW_MAX_ROWS = 5
PREVIEW_MAX_COLUMNS = 50
PREVIEW_MAX_CELL_CHARS = 200


@dataclass(frozen=True)
class CsvPreview:
    rows: list[list[str]]
    truncated: bool


def validate_csv_format(binary_file: BinaryIO) -> CsvPreview:
    """从头解析完整文件，保留前几条记录，不推断表头或检查业务数据。

    预览限制只作用于返回内容；底层原始文件始终由调用方管理。
    同步读取和解析可能耗时，异步接口应在线程池中调用本函数。
    """
    binary_file.seek(0)
    text_stream = io.TextIOWrapper(binary_file, encoding="utf-8-sig", errors="strict", newline="")
    reader = csv.reader(
        text_stream, delimiter=",", quotechar='"', doublequote=True, strict=True,
    )
    preview_rows = []
    truncated = False
    try:
        for row in reader:
            if len(preview_rows) < PREVIEW_MAX_ROWS:
                visible_cells = row[:PREVIEW_MAX_COLUMNS]
                preview_rows.append([cell[:PREVIEW_MAX_CELL_CHARS] for cell in visible_cells])
                if len(row) > PREVIEW_MAX_COLUMNS or any(
                    len(cell) > PREVIEW_MAX_CELL_CHARS for cell in visible_cells
                ):
                    truncated = True
            else:
                # 仍继续解析后续记录，防止预览范围外的格式错误被漏过。
                truncated = True
    except csv.Error as error:
        raise InvalidCsvFormatError(reader.line_num or 1) from error
    except UnicodeDecodeError as error:
        raise InvalidFileEncodingError(
            "文件无法按 UTF-8 解码，请另存为 UTF-8 编码后重新上传",
        ) from error
    finally:
        # 解除文本包装，避免包装器提前关闭 FastAPI 管理的临时文件。
        text_stream.detach()

    return CsvPreview(rows=preview_rows, truncated=truncated)


def read_file_columns(binary_file: BinaryIO, has_header: bool) -> tuple[FileColumn, ...]:
    """按相同 CSV 规则读取完整列信息，不使用截断预览，不修改原文件。

    有表头时严格使用首条记录；无表头时以首条含字段的记录确定列数，
    此处只读取列结构，不改变后续数据处理对原始记录的读取。
    """
    binary_file.seek(0)
    text_stream = io.TextIOWrapper(binary_file, encoding="utf-8-sig", errors="strict", newline="")
    reader = csv.reader(text_stream, delimiter=",", quotechar='"', doublequote=True, strict=True)
    try:
        for row in reader:
            if has_header or row:
                return build_file_columns(row, has_header)
        raise InvalidFileHeaderError("文件中没有可用于确定列信息的记录")
    except csv.Error as error:
        raise InvalidCsvFormatError(reader.line_num or 1) from error
    except UnicodeDecodeError as error:
        raise InvalidFileEncodingError("文件无法按 UTF-8 解码，请另存为 UTF-8 编码后重新上传") from error
    finally:
        text_stream.detach()
