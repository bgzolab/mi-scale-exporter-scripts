import contextlib
import io
import unittest
from unittest.mock import patch

from mi_scale_exporter.cli import _warn_extension_mismatch
from mi_scale_exporter.export import (
    _normalize_fractional_seconds,
    open_output,
    parse_time,
)


class ExportTimeTest(unittest.TestCase):
    def test_fractional_seconds_are_normalized(self):
        self.assertEqual(
            _normalize_fractional_seconds("2025-01-01T00:00:00.1+08:00"),
            "2025-01-01T00:00:00.100000+08:00",
        )
        self.assertEqual(
            _normalize_fractional_seconds("2025-01-01T00:00:00.1234567Z"),
            "2025-01-01T00:00:00.123456Z",
        )

    def test_parse_iso_fractional_seconds(self):
        parsed = parse_time("2025-01-01T00:00:00.1")
        self.assertEqual(parsed.microsecond, 100000)

    def test_stdout_csv_has_bom(self):
        raw = io.BytesIO()
        fake_stdout = io.TextIOWrapper(raw, encoding="utf-8")
        with patch("sys.stdout", fake_stdout):
            handle, should_close = open_output("-", "csv")
            handle.write("a,b\n")
            handle.flush()
        self.assertFalse(should_close)
        self.assertTrue(raw.getvalue().startswith(b"\xef\xbb\xbf"))

    def test_stdout_json_has_no_bom(self):
        raw = io.BytesIO()
        fake_stdout = io.TextIOWrapper(raw, encoding="utf-8")
        with patch("sys.stdout", fake_stdout):
            handle, should_close = open_output("-", "json")
            handle.write('{"a": 1}\n')
            handle.flush()
        self.assertFalse(should_close)
        self.assertFalse(raw.getvalue().startswith(b"\xef\xbb\xbf"))
        self.assertEqual(raw.getvalue().decode("utf-8"), '{"a": 1}\n')

    def test_extension_mismatch_warnings(self):
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            _warn_extension_mismatch("json", "weights.csv")
        self.assertIn("JSON", buffer.getvalue())

        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            _warn_extension_mismatch("csv", "weights.json")
        self.assertIn("CSV", buffer.getvalue())

        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            _warn_extension_mismatch("csv", "weights.csv")
        self.assertEqual(buffer.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
