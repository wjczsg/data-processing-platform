"""按固定的逗号、双引号规则逐条校验 CSV 语法。"""

import csv
import io
from typing import BinaryIO

from backend.app.domain.file_rules import InvalidCsvFormatError, InvalidFileEncodingError

# 标准库默认只允许 128 KiB 单字段，会误拒当前上传上限内的长字段。
# 进程加载时统一放宽，不在并发请求中修改全局配置；文件总大小由上传接口限制。
csv.field_size_limit(max(csv.field_size_limit(), 2**31 - 1))


def validate_csv_format(binary_file: BinaryIO) -> None:
    """从头解析完整文件，不检查模板或业务数据；底层文件始终由调用方关闭。

    同步读取和解析可能耗时，异步接口应在线程池中调用本函数。
    """
    binary_file.seek(0)
    text_stream = io.TextIOWrapper(binary_file, encoding="utf-8-sig", errors="strict", newline="")
    reader = csv.reader(
        text_stream, delimiter=",", quotechar='"', doublequote=True, strict=True,
    )
    try:
        for _ in reader:
            pass
    except csv.Error as error:
        raise InvalidCsvFormatError(reader.line_num or 1) from error
    except UnicodeDecodeError as error:
        raise InvalidFileEncodingError(
            "文件无法按 UTF-8 解码，请另存为 UTF-8 编码后重新上传",
        ) from error
    finally:
        # 解除文本包装，避免包装器提前关闭 FastAPI 管理的临时文件。
        text_stream.detach()
