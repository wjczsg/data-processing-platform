"""验证真实 Argon2id 哈希生成、密码验证及项目异常转换，不访问数据库。"""

import unittest
from unittest.mock import patch

from argon2 import PasswordHasher as Argon2LibraryHasher, extract_parameters
from argon2.exceptions import (
    HashingError,
    UnsupportedParametersError,
    VerificationError,
    VerifyMismatchError,
)
from argon2.low_level import Type

from backend.app.application.ports.password_hasher import PasswordHasher, PasswordHashError
from backend.app.domain.password import validate_new_password
from backend.app.domain.user import PASSWORD_HASH_MAX_LENGTH
from backend.app.infrastructure.security.password_hasher import Argon2PasswordHasher


class PasswordHashingTests(unittest.TestCase):
    def setUp(self):
        self.hasher = Argon2PasswordHasher()
        self.library_hasher = Argon2LibraryHasher()

    def test_generated_hash_is_argon2id_verifiable_and_fits_database_field(self):
        password = "LearningPython42!"
        validate_new_password(password)
        encoded = self.hasher.hash_password(password)

        self.assertIsInstance(encoded, str)
        self.assertEqual(extract_parameters(encoded).type, Type.ID)
        self.assertLessEqual(len(encoded), PASSWORD_HASH_MAX_LENGTH)
        self.assertTrue(self.library_hasher.verify(encoded, password))

    def test_same_password_uses_different_random_salts(self):
        password = "LearningPython42!"
        first = self.hasher.hash_password(password)
        second = self.hasher.hash_password(password)
        self.assertNotEqual(first.split("$")[4], second.split("$")[4])
        self.assertTrue(self.library_hasher.verify(first, password))
        self.assertTrue(self.library_hasher.verify(second, password))

    def test_spaces_case_and_unicode_are_preserved(self):
        password = "  LearnPython你好  "
        validate_new_password(password)
        encoded = self.hasher.hash_password(password)
        self.assertTrue(self.library_hasher.verify(encoded, password))
        for changed in (password.strip(), password.lower()):
            with self.assertRaises(VerifyMismatchError):
                self.library_hasher.verify(encoded, changed)

    def test_maximum_length_unicode_password_is_not_truncated(self):
        password = "😀" * 128
        validate_new_password(password)
        encoded = self.hasher.hash_password(password)
        self.assertTrue(self.library_hasher.verify(encoded, password))
        with self.assertRaises(VerifyMismatchError):
            self.library_hasher.verify(encoded, password[:-1])

    def test_library_and_random_source_failures_are_translated(self):
        for error in (HashingError("simulated hashing failure"), OSError("simulated random source failure")):
            with self.subTest(error=type(error).__name__):
                with patch(
                    "backend.app.infrastructure.security.password_hasher.Argon2LibraryHasher.hash",
                    side_effect=error,
                ):
                    with self.assertRaises(PasswordHashError) as result:
                        self.hasher.hash_password("LearningPython42!")
                    self.assertIs(result.exception.__cause__, error)
                    self.assertNotIn("LearningPython42!", str(result.exception))

    def test_invalid_input_is_reported_as_password_hash_error(self):
        for password in (None, 12345678, b"abcdefgh", "abcdefgh\ud800"):
            with self.subTest(password=repr(password)), self.assertRaises(PasswordHashError):
                self.hasher.hash_password(password)


class PasswordVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hasher: PasswordHasher = Argon2PasswordHasher()
        cls.password = "  LearnPython你好  "
        cls.encoded = cls.hasher.hash_password(cls.password)

    def test_correct_password_returns_true(self):
        self.assertIs(self.hasher.verify_password(self.password, self.encoded), True)

    def test_incorrect_password_returns_false(self):
        self.assertIs(self.hasher.verify_password("AnotherPassword42!", self.encoded), False)

    def test_spaces_case_and_unicode_are_not_changed(self):
        for changed in (self.password.strip(), self.password.lower(), self.password.replace("你好", "您好")):
            with self.subTest(password=changed):
                self.assertIs(self.hasher.verify_password(changed, self.encoded), False)

    def test_each_saved_random_salt_is_used_for_verification(self):
        another_hash = self.hasher.hash_password(self.password)
        self.assertNotEqual(another_hash, self.encoded)
        self.assertTrue(self.hasher.verify_password(self.password, another_hash))
        self.assertTrue(self.hasher.verify_password(self.password, self.encoded))

    def test_login_does_not_reapply_new_password_policy(self):
        # 模拟旧规则下创建的短密码；验证已有凭据不受新密码长度规则影响。
        old_password = "short"
        with self.assertRaises(ValueError):
            validate_new_password(old_password)
        old_hash = Argon2LibraryHasher().hash(old_password)
        self.assertTrue(self.hasher.verify_password(old_password, old_hash))
        self.assertFalse(self.hasher.verify_password("wrong", old_hash))

    def test_invalid_stored_hash_raises_instead_of_returning_false(self):
        for encoded in ("", "not-a-hash", "$argon2id$v=19$m=bad,t=3,p=4$salt$hash", "无效哈希"):
            with self.subTest(encoded=encoded), self.assertRaises(PasswordHashError):
                self.hasher.verify_password(self.password, encoded)

    def test_invalid_inputs_raise_project_error(self):
        for password, encoded in (
            (None, self.encoded),
            (b"password", self.encoded),
            ("password", None),
            ("password", 123),
            ("password", self.encoded.encode("ascii")),
            ("abcdefgh\ud800", self.encoded),
        ):
            with self.subTest(password=repr(password), hash_type=type(encoded).__name__):
                with self.assertRaises(PasswordHashError):
                    self.hasher.verify_password(password, encoded)

    def test_processing_failure_is_translated_without_password_in_message(self):
        for error in (
            VerificationError("simulated verification failure"),
            UnsupportedParametersError("simulated unsupported parameters"),
        ):
            with self.subTest(error=type(error).__name__):
                with patch(
                    "backend.app.infrastructure.security.password_hasher.Argon2LibraryHasher.verify",
                    side_effect=error,
                ):
                    with self.assertRaises(PasswordHashError) as result:
                        self.hasher.verify_password(self.password, self.encoded)
                    self.assertIs(result.exception.__cause__, error)
                    self.assertNotIn(self.password, str(result.exception))
                    self.assertNotIn(self.encoded, str(result.exception))


if __name__ == "__main__":
    unittest.main()
