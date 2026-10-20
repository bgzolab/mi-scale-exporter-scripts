"""CSV/JSON output helpers."""

from __future__ import annotations

import csv
import json
import sys
from datetime import date, datetime, time
from pathlib import Path
from typing import Iterable, List, Optional, TextIO

from .parser import EXTRA_COLUMNS, MAIN_COLUMNS, Measurement


def parse_time(value: str, end_of_day: bool = False) -> datetime:
    """Parse ``YYYY-MM-DD`` or ISO-8601 and attach the local timezone if needed."""
    text = value.strip()
    if not text:
        raise ValueError("时间不能为空")
    try:
        if len(text) == 10:
            day = date.fromisoformat(text)
            parsed = datetime.combine(day, time.max if end_of_day else time.min)
        else:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"无法解析时间 {value!r}，请使用 YYYY-MM-DD 或 ISO-8601") from exc

    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def to_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def write_csv(handle: TextIO, measurements: Iterable[Measurement], full: bool = False, utc: bool = False) -> None:
    columns: List[str] = list(MAIN_COLUMNS)
    if full:
        columns.extend(column for column, _ in EXTRA_COLUMNS)
    writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for measurement in measurements:
        writer.writerow(measurement.to_row(full=full, utc=utc))


def write_json(
    handle: TextIO,
    measurements: Iterable[Measurement],
    full: bool = False,
    utc: bool = False,
) -> None:
    payload = [measurement.to_dict(full=full, utc=utc) for measurement in measurements]
    json.dump(payload, handle, ensure_ascii=False, indent=2)
    handle.write("\n")


def write_raw_json(handle: TextIO, records: Iterable[dict]) -> None:
    json.dump(list(records), handle, ensure_ascii=False, indent=2)
    handle.write("\n")


def output_format(path: Optional[str], requested: Optional[str], raw: bool = False) -> str:
    if requested:
        return requested
    if raw:
        return "json"
    if path and path.lower().endswith(".json"):
        return "json"
    return "csv"


def open_output(path: Optional[str], fmt: str):
    """Return ``(handle, should_close)`` for stdout or a file path."""
    if not path or path == "-":
        return sys.stdout, False
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoding = "utf-8-sig" if fmt == "csv" else "utf-8"
    newline = "" if fmt == "csv" else None
    return target.open("w", encoding=encoding, newline=newline), True
