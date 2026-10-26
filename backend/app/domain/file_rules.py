"""上传文件的业务规则，不依赖 HTTP、数据库或具体存储方式。"""

from pathlib import PurePath


def validate_csv_filename(filename: str | None) -> None:
    """只允许 .csv 扩展名，忽略大小写；文件内容合法性由后续解析确认。"""
    if not filename or PurePath(filename).suffix.lower() != ".csv":
        raise ValueError("仅支持上传 CSV 文件（.csv）")
