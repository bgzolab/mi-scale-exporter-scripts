import json
import os
import tempfile
import unittest
from pathlib import Path

from mi_scale_exporter.config import load_config, save_config


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


if __name__ == "__main__":
    unittest.main()
