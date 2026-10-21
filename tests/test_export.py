import unittest

from mi_scale_exporter.export import _normalize_fractional_seconds, parse_time


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


if __name__ == "__main__":
    unittest.main()
