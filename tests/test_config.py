import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mi_scale_exporter.config import load_config, load_env_file, save_config


class ConfigTest(unittest.TestCase):
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "credentials.json"
            save_config({"user_id": 123, "pass_token": "secret"}, path)
            self.assertTrue(path.exists())
            self.assertEqual(load_config(path)["user_id"], 123)
            self.assertEqual(load_config(path)["pass_token"], "secret")
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_missing_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_config(Path(tmp) / "missing.json"), {})

    def test_env_key_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("XIAOMI_USER_ID=123\nXIAOMI_PASS_TOKEN=V1:abc=def\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                values = load_env_file(path)
                self.assertEqual(values["user_id"], "123")
                self.assertEqual(values["pass_token"], "V1:abc=def")
                self.assertEqual(os.environ["XIAOMI_USER_ID"], "123")
                self.assertEqual(os.environ["XIAOMI_PASS_TOKEN"], "V1:abc=def")

    def test_env_raw_two_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("123456789\nV1:fake-token-with=equals\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                values = load_env_file(path)
                self.assertEqual(values["user_id"], "123456789")
                self.assertTrue(values["pass_token"].startswith("V1:"))
                self.assertEqual(os.environ["XIAOMI_USER_ID"], "123456789")

    def test_env_does_not_override_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("XIAOMI_USER_ID=123\nXIAOMI_PASS_TOKEN=from-file\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {"XIAOMI_USER_ID": "999", "XIAOMI_PASS_TOKEN": "from-env"},
                clear=True,
            ):
                load_env_file(path)
                self.assertEqual(os.environ["XIAOMI_USER_ID"], "999")
                self.assertEqual(os.environ["XIAOMI_PASS_TOKEN"], "from-env")


if __name__ == "__main__":
    unittest.main()
