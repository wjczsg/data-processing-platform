"""验证 CSV 组件的流位置、文件所有权与错误转换。"""

import io
import unittest

from backend.app.domain.file_rules import InvalidCsvFormatError, InvalidFileEncodingError
from backend.app.infrastructure.files.csv_format import validate_csv_format


class CsvFormatTests(unittest.TestCase):
    def test_valid_stream_remains_open_and_can_be_read_again(self):
        content = b"a,b\n1,2\n"
        with io.BytesIO(content) as stream:
            stream.seek(0, io.SEEK_END)
            validate_csv_format(stream)
            self.assertFalse(stream.closed)
            stream.seek(0)
            self.assertEqual(stream.read(), content)

    def test_invalid_stream_is_rewound_and_remains_open_after_error(self):
        with io.BytesIO(b'a,b\n1,"line1\nline2"\n2,"unfinished') as stream:
            stream.seek(0, io.SEEK_END)
            with self.assertRaises(InvalidCsvFormatError) as result:
                validate_csv_format(stream)
            self.assertEqual(result.exception.line_number, 4)
            self.assertFalse(stream.closed)

    def test_encoding_error_is_translated_without_closing_caller_stream(self):
        with io.BytesIO(b"a,b\n1,\xff\n") as stream:
            with self.assertRaises(InvalidFileEncodingError):
                validate_csv_format(stream)
            self.assertFalse(stream.closed)


if __name__ == "__main__":
    unittest.main()
