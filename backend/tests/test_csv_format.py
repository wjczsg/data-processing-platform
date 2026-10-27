"""验证 CSV 组件的流位置、文件所有权与错误转换。"""

import io
import unittest

from backend.app.domain.file_rules import InvalidCsvFormatError, InvalidFileEncodingError
from backend.app.infrastructure.files.csv_format import validate_csv_format


class CsvFormatTests(unittest.TestCase):
    def test_preview_keeps_first_five_records_in_order_without_header_inference(self):
        records = [[f"{number:03}", f" value {number} "] for number in range(7)]
        content = "\n".join(",".join(record) for record in records).encode()
        with io.BytesIO(content) as stream:
            preview = validate_csv_format(stream)
        self.assertEqual(preview.rows, records[:5])
        self.assertTrue(preview.truncated)

    def test_preview_is_not_marked_truncated_when_all_records_fit(self):
        for count in (0, 1, 5):
            with self.subTest(count=count), io.BytesIO(b"a,b\n" * count) as stream:
                preview = validate_csv_format(stream)
                self.assertEqual(preview.rows, [["a", "b"]] * count)
                self.assertFalse(preview.truncated)

    def test_preview_limits_columns_and_cell_length_without_modifying_original_file(self):
        for columns, cell_length in ((50, 200), (51, 200), (50, 201)):
            content = ",".join(["x" * cell_length] * columns).encode()
            with self.subTest(columns=columns, cell_length=cell_length), io.BytesIO(content) as stream:
                preview = validate_csv_format(stream)
                self.assertEqual(preview.rows, [["x" * 200] * 50])
                self.assertEqual(preview.truncated, columns > 50 or cell_length > 200)
                stream.seek(0)
                self.assertEqual(stream.read(), content)

    def test_preview_counts_records_and_preserves_multiline_fields_and_escaped_quotes(self):
        content = b'\xef\xbb\xbf1,"line1\nline2"\n2,"with,comma"\n3,"say""yes"""\n4,plain\n5,last\n'
        with io.BytesIO(content) as stream:
            preview = validate_csv_format(stream)
        self.assertEqual(preview.rows, [
            ["1", "line1\nline2"], ["2", "with,comma"], ["3", 'say"yes"'],
            ["4", "plain"], ["5", "last"],
        ])
        self.assertFalse(preview.truncated)

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
