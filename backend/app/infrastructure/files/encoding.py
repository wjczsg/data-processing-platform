"""使用标准库增量解码器检查 UTF-8，兼容开头的 UTF-8 BOM。"""

import codecs

from backend.app.domain.file_rules import InvalidFileEncodingError


class Utf8FileValidator:
    """每个文件独立创建实例；保留跨块字节，不累计完整文件内容。"""

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8-sig")(errors="strict")

    def validate_chunk(self, chunk: bytes) -> None:
        self._decode(chunk, final=False)

    def finish(self) -> None:
        """读取结束后检查未完成的字符，必须在最后一个数据块后调用。"""
        self._decode(b"", final=True)

    def _decode(self, chunk: bytes, *, final: bool) -> None:
        message = "文件无法按 UTF-8 解码，请另存为 UTF-8 编码后重新上传"
        try:
            self._decoder.decode(chunk, final=final)
        except UnicodeDecodeError as error:
            raise InvalidFileEncodingError(message) from error

        # 部分 Python 版本在 EOF 遇到不完整的 BOM 时仍保留缓冲，需显式拒绝。
        if final and self._decoder.getstate()[0]:
            raise InvalidFileEncodingError(message)
