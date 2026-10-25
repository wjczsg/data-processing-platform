"""验证新密码规则的边界、Unicode 计数与原始输入保护。"""

import unittest

from backend.app.domain.password import (
    validate_new_password,
    validate_password_confirmation,
)


class PasswordPolicyTests(unittest.TestCase):
    def test_length_boundaries(self):
        for password in ("a" * 8, "a" * 128):
            with self.subTest(length=len(password)):
                self.assertIsNone(validate_new_password(password))
        for password in ("", "a" * 7, "a" * 129):
            with self.subTest(length=len(password)), self.assertRaises(ValueError):
                validate_new_password(password)

    def test_unicode_length_counts_codepoints_not_bytes(self):
        for password in ("学" * 8, "😀" * 128):
            self.assertIsNone(validate_new_password(password))
        with self.assertRaises(ValueError):
            validate_new_password("😀" * 129)

    def test_all_whitespace_and_control_characters_are_rejected(self):
        for password in (
            " " * 8, "\u3000" * 8, "abcd\nefgh", "abcd\refgh",
            "abcd\tefgh", "abcd\x00efgh", "abcd\x7fefgh",
            "abcd\u2028efgh", "abcd\u2029efgh", "abcd\ud800efgh",
        ):
            with self.subTest(password=repr(password)), self.assertRaises(ValueError):
                validate_new_password(password)

    def test_common_passwords_are_rejected_case_insensitively(self):
        for password in ("12345678", "password", "PassWord", "PASSWORD123"):
            with self.subTest(password=password), self.assertRaises(ValueError):
                validate_new_password(password)

    def test_no_character_mixture_required_and_spaces_are_preserved(self):
        for password in ("abcdefgh", "雨后一起去公园散步", " my phrase "):
            self.assertIsNone(validate_new_password(password))
            self.assertIsNone(validate_password_confirmation(password, password))
        for confirmation in ("my phrase", " MY PHRASE "):
            with self.assertRaises(ValueError):
                validate_password_confirmation(" my phrase ", confirmation)

    def test_invalid_input_types(self):
        for value in (None, 12345678, b"abcdefgh"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_new_password(value)
            with self.assertRaises(ValueError):
                validate_password_confirmation("abcdefgh", value)

    def test_error_message_does_not_contain_submitted_password(self):
        password = "PrivateExample\n42"
        with self.assertRaises(ValueError) as result:
            validate_new_password(password)
        self.assertNotIn(password, str(result.exception))


if __name__ == "__main__":
    unittest.main()
