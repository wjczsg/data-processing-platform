"""验证 MySQL 配置的读取、约束和密码处理。"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import SecretStr, ValidationError

from backend.app.core.config import Settings


class MySQLConfigTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ)
        self.environment.start()
        known_keys = {name.upper() for name in Settings.model_fields}
        for key in list(os.environ):
            if key.upper() in known_keys:
                del os.environ[key]

    def tearDown(self):
        self.environment.stop()

    def settings(self, **overrides):
        values = {"mysql_user": "test_user", "mysql_password": "sample-password"}
        values.update(overrides)
        return Settings(_env_file=None, **values)

    def test_connection_defaults_and_port_conversion(self):
        settings = self.settings(mysql_port="3307")
        self.assertEqual(settings.mysql_host, "127.0.0.1")
        self.assertEqual(settings.mysql_database, "data_processing_platform")
        self.assertEqual(settings.mysql_port, 3307)
        self.assertIsInstance(settings.mysql_port, int)

    def test_upload_limit_defaults_to_50_mib_and_requires_a_positive_integer(self):
        self.assertEqual(self.settings().upload_max_bytes, 52428800)
        os.environ["UPLOAD_MAX_BYTES"] = "8"
        self.assertEqual(self.settings().upload_max_bytes, 8)
        for invalid in (0, -1, "abc"):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                self.settings(upload_max_bytes=invalid)

    def test_port_and_empty_text_are_rejected(self):
        for port in (0, 65536, "abc"):
            with self.subTest(port=port), self.assertRaises(ValidationError):
                self.settings(mysql_port=port)
        for field in ("mysql_host", "mysql_database", "mysql_user"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.settings(**{field: "   "})

    def test_credentials_are_required_and_password_cannot_be_empty(self):
        with self.assertRaises(ValidationError):
            Settings(_env_file=None)
        with self.assertRaises(ValidationError):
            self.settings(mysql_password="")

    def test_password_is_preserved_and_masked(self):
        password = "  001234@sample  "
        settings = self.settings(mysql_password=password)
        self.assertIsInstance(settings.mysql_password, SecretStr)
        self.assertEqual(settings.mysql_password.get_secret_value(), password)
        self.assertNotIn(password, repr(settings))
        self.assertNotIn(password, settings.model_dump_json())
        self.assertIn("**********", settings.model_dump_json())

    def test_dotenv_loading_and_environment_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                'MYSQL_HOST=localhost\nMYSQL_PORT=3306\n'
                'MYSQL_DATABASE=demo\nMYSQL_USER=test_user\n'
                'MYSQL_PASSWORD="001234"\n',
                encoding="utf-8",
            )
            settings = Settings(_env_file=path)
            self.assertEqual(settings.mysql_password.get_secret_value(), "001234")
            self.assertEqual(settings.mysql_port, 3306)
            os.environ["MYSQL_PORT"] = "3308"
            self.assertEqual(Settings(_env_file=path).mysql_port, 3308)

    def test_validation_error_text_hides_input(self):
        invalid_port = "invalid-sensitive-input"
        with self.assertRaises(ValidationError) as result:
            self.settings(mysql_port=invalid_port)
        self.assertNotIn(invalid_port, str(result.exception))

    def test_jwt_key_is_masked_and_lifetime_is_bounded(self):
        key = "test-only-jwt-key-" + "x" * 32
        settings = self.settings(jwt_secret_key=key)
        self.assertEqual(settings.jwt_secret_key.get_secret_value(), key)
        self.assertNotIn(key, repr(settings))
        self.assertNotIn(key, settings.model_dump_json())
        self.assertEqual(settings.jwt_access_token_expire_minutes, 30)
        for invalid_key in ("short", " " * 32):
            with self.assertRaises(ValidationError):
                self.settings(jwt_secret_key=invalid_key)
        for minutes in (0, 1441):
            with self.assertRaises(ValidationError):
                self.settings(jwt_access_token_expire_minutes=minutes)


if __name__ == "__main__":
    unittest.main()
