"""Parse Xiaomi Cloud scale records into a stable, flat measurement model."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

MAIN_COLUMNS = [
    "date",
    "weight_kg",
    "bmi",
    "body_fat_pct",
    "body_water_pct",
    "bone_mass_kg",
    "metabolic_age",
    "muscle_mass_kg",
    "protein_mass_kg",
    "visceral_fat",
    "basal_metabolism_kcal",
    "body_score",
    "heart_rate_bpm",
    "skeletal_muscle_mass_kg",
    "physique_rating",
    "height_cm",
    "user",
    "source",
    "model",
    "from_source",
]

# S800-specific segmental values (in addition to the common fields above).
EXTRA_COLUMNS = [
    ("right_arm_muscle_kg", "ram"),
    ("left_arm_muscle_kg", "lam"),
    ("right_leg_muscle_kg", "rlm"),
    ("left_leg_muscle_kg", "llm"),
    ("trunk_muscle_kg", "tm"),
    ("right_arm_muscle_pct", "ram_p"),
    ("left_arm_muscle_pct", "lam_p"),
    ("right_leg_muscle_pct", "rlm_p"),
    ("left_leg_muscle_pct", "llm_p"),
    ("trunk_muscle_pct", "tm_p"),
    ("right_arm_muscle_score", "ram_s"),
    ("left_arm_muscle_score", "lam_s"),
    ("right_leg_muscle_score", "rlm_s"),
    ("left_leg_muscle_score", "llm_s"),
    ("trunk_muscle_score", "tm_s"),
    ("right_arm_fat_kg", "rafm"),
    ("left_arm_fat_kg", "larm"),
    ("right_leg_fat_kg", "rlfm"),
    ("left_leg_fat_kg", "llfm"),
    ("trunk_fat_kg", "tfm"),
    ("right_arm_fat_pct", "rafm_p"),
    ("left_arm_fat_pct", "lafm_p"),
    ("right_leg_fat_pct", "rlfm_p"),
    ("left_leg_fat_pct", "llfm_p"),
    ("trunk_fat_pct", "tfm_p"),
    ("right_arm_fat_score", "rafm_s"),
    ("left_arm_fat_score", "larm_s"),
    ("right_leg_fat_score", "rlfm_s"),
    ("left_leg_fat_score", "llfm_s"),
    ("trunk_fat_score", "tfm_s"),
    ("limb_bmi", "limbmi"),
    ("recommended_calorie_intake_kcal", "cin"),
    ("body_type", "bs"),
    ("protein_pct", "pp"),
    ("muscle_pct", "slp"),
    ("bone_pct", "bmcp"),
    ("fat_mass_kg", "bfm"),
    ("fat_free_mass_kg", "ffm"),
    ("body_water_mass_kg", "bwm"),
    ("waist_hip_ratio", "whr"),
    ("standard_weight_kg", "swt"),
    ("muscle_control_kg", "mc"),
    ("weight_control_kg", "wc"),
    ("fat_control_kg", "fc"),
    ("smi", "smi"),
    ("eoma", "eoma"),
    ("eoml", "eoml"),
    ("eomb", "eomb"),
    ("eofa", "eofa"),
    ("eofl", "eofl"),
    ("eofb", "eofb"),
    ("bfp_state", "bfp_state"),
]


@dataclass
class Measurement:
    measured_at_ms: int
    measured_at: datetime
    weight_kg: Optional[float] = None
    bmi: Optional[float] = None
    body_fat_pct: Optional[float] = None
    body_water_pct: Optional[float] = None
    bone_mass_kg: Optional[float] = None
    metabolic_age: Optional[int] = None
    muscle_mass_kg: Optional[float] = None
    protein_mass_kg: Optional[float] = None
    visceral_fat: Optional[int] = None
    basal_metabolism_kcal: Optional[int] = None
    body_score: Optional[int] = None
    heart_rate_bpm: Optional[int] = None
    skeletal_muscle_mass_kg: Optional[float] = None
    physique_rating: Optional[int] = None
    height_cm: Optional[float] = None
    user: Optional[str] = None
    source: Optional[str] = None
    model: Optional[str] = None
    from_source: Optional[int] = None
    extras: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    def richness(self) -> int:
        values = [
            self.weight_kg,
            self.bmi,
            self.body_fat_pct,
            self.body_water_pct,
            self.bone_mass_kg,
            self.metabolic_age,
            self.muscle_mass_kg,
            self.protein_mass_kg,
            self.visceral_fat,
            self.basal_metabolism_kcal,
            self.body_score,
            self.heart_rate_bpm,
            self.skeletal_muscle_mass_kg,
            self.physique_rating,
            self.height_cm,
        ]
        return sum(v is not None for v in values) + len(self.extras)

    def to_row(self, full: bool = False, utc: bool = False) -> Dict[str, Any]:
        date = self.measured_at.astimezone(timezone.utc if utc else None).isoformat(
            timespec="seconds"
        )
        row: Dict[str, Any] = {
            "date": date,
            "weight_kg": self.weight_kg,
            "bmi": self.bmi,
            "body_fat_pct": self.body_fat_pct,
            "body_water_pct": self.body_water_pct,
            "bone_mass_kg": self.bone_mass_kg,
            "metabolic_age": self.metabolic_age,
            "muscle_mass_kg": self.muscle_mass_kg,
            "protein_mass_kg": self.protein_mass_kg,
            "visceral_fat": self.visceral_fat,
            "basal_metabolism_kcal": self.basal_metabolism_kcal,
            "body_score": self.body_score,
            "heart_rate_bpm": self.heart_rate_bpm,
            "skeletal_muscle_mass_kg": self.skeletal_muscle_mass_kg,
            "physique_rating": self.physique_rating,
            "height_cm": self.height_cm,
            "user": self.user,
            "source": self.source,
            "model": self.model,
            "from_source": self.from_source,
        }
        if full:
            for column, key in EXTRA_COLUMNS:
                row[column] = self.extras.get(key)
        return row

    def to_dict(self, full: bool = False, utc: bool = False) -> Dict[str, Any]:
        data = self.to_row(full=False, utc=utc)
        if full:
            data["extras"] = self.extras
            data["raw"] = self.raw
        return data


def _as_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _as_int(value: Any) -> Optional[int]:
    number = _as_float(value)
    return int(number) if number is not None else None


MAX_TIMESTAMP_MS = 32_503_680_000_000  # 3000-01-01, avoids platform overflow


def _as_ms(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = int(value)
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            number = int(float(text))
        except ValueError:
            return None
    if 10**12 < number <= MAX_TIMESTAMP_MS:
        return number
    if 10**9 < number <= MAX_TIMESTAMP_MS // 1000:
        return number * 1000
    return None


def _nested(data: Dict[str, Any], key: str) -> Any:
    current: Any = data
    for part in key.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _parse_json_object(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def parse_record(item: Dict[str, Any]) -> Optional[Measurement]:
    """Parse one raw record returned by ``/eco/scale/getData``."""
    data = _parse_json_object(item.get("data"))
    if not data:
        return None

    body = _parse_json_object(data.get("bodyResData"))
    # Top-level keys (weight/bmi/heartRate/user/time) take precedence over
    # bodyResData, which contains the detailed body-composition fields.
    merged: Dict[str, Any] = {**body, **data}

    weight = _as_float(merged.get("weight"))
    if weight is None or weight <= 0:
        return None

    from_source = _as_int(item.get("fromSource"))

    create_ms = _as_ms(item.get("createTime"))
    time_ms = _as_ms(data.get("time"))
    # For fromSource=3 the top-level time is the measurement time.  Older
    # source types have known bugs in their time field, so use createTime.
    if from_source == 3:
        measured_at_ms = time_ms or create_ms
    else:
        measured_at_ms = create_ms or time_ms
    if measured_at_ms is None:
        return None

    user_name = _nested(merged, "user.name")
    if user_name is None:
        user_name = merged.get("userName") or merged.get("user_name")

    height = _nested(merged, "user.height")
    if height is None:
        height = merged.get("height")

    if from_source == 1:
        source = merged.get("reportFrom")
    elif from_source == 2:
        source = _nested(merged, "user.deviceId") or item.get("did") or data.get("mid")
    elif from_source == 3:
        source = item.get("did") or data.get("mid")
    else:
        source = item.get("did") or data.get("mid") or _nested(merged, "user.deviceId")

    extras = {
        key: value
        for key, value in {**body, **data}.items()
        if key
        not in {
            "weight",
            "bmi",
            "bfp",
            "bwp",
            "bmc",
            "ma",
            "slm",
            "pm",
            "vfl",
            "bmr",
            "sbc",
            "heartRate",
            "heart_rate",
            "smm",
            "bt",
            "time",
            "user",
            "userName",
            "user_name",
            "height",
            "bodyResData",
            "reportFrom",
            "mid",
            "did",
        }
    }

    return Measurement(
        measured_at_ms=measured_at_ms,
        measured_at=datetime.fromtimestamp(measured_at_ms / 1000, tz=timezone.utc),
        weight_kg=weight,
        bmi=_as_float(merged.get("bmi")),
        body_fat_pct=_as_float(merged.get("bfp")),
        body_water_pct=_as_float(merged.get("bwp")),
        bone_mass_kg=_as_float(merged.get("bmc")),
        metabolic_age=_as_int(merged.get("ma")),
        muscle_mass_kg=_as_float(merged.get("slm")),
        protein_mass_kg=_as_float(merged.get("pm")),
        visceral_fat=_as_int(merged.get("vfl")),
        basal_metabolism_kcal=_as_int(merged.get("bmr")),
        body_score=_as_int(merged.get("sbc")),
        heart_rate_bpm=_as_int(merged.get("heartRate") or merged.get("heart_rate")),
        skeletal_muscle_mass_kg=_as_float(merged.get("smm")),
        physique_rating=_as_int(merged.get("bt")),
        height_cm=_as_float(height),
        user=str(user_name) if user_name is not None else None,
        source=str(source) if source is not None else None,
        model=item.get("model"),
        from_source=from_source,
        extras=extras,
        raw={"data": data, "bodyResData": body},
    )


def parse_records(items: Iterable[Dict[str, Any]]) -> List[Measurement]:
    measurements = []
    for item in items:
        if not isinstance(item, dict):
            continue
        measurement = parse_record(item)
        if measurement is not None:
            measurements.append(measurement)
    return measurements


def dedupe_measurements(measurements: Iterable[Measurement]) -> List[Measurement]:
    """Keep the richest record for records with the same time/user/weight."""
    best: Dict[tuple, Measurement] = {}
    for measurement in measurements:
        key = (
            measurement.measured_at_ms,
            measurement.user or "",
            round(measurement.weight_kg or 0.0, 3),
        )
        current = best.get(key)
        if current is None or measurement.richness() > current.richness():
            best[key] = measurement
    return sorted(best.values(), key=lambda m: m.measured_at_ms)
