import unittest

from mi_scale_exporter.parser import dedupe_measurements, parse_record, parse_records


def s800_item(create_ms=1755927448000, weight="63.15", body_fat="16.5"):
    body = {
        "bfp": body_fat,
        "bwp": "61.8",
        "bmc": "2.9",
        "ma": "35.0",
        "slm": "49.8",
        "pm": "10.3",
        "vfl": "4.0",
        "bmr": "1508.0",
        "sbc": "79.0",
        "smm": "28.6",
        "bt": "4.0",
        "ram": "2.7",
        "lam": "2.6",
        "rlm": "8.7",
        "llm": "8.7",
        "tm": "23.6",
        "ram_p": "83.1",
        "cin": "2187.0",
    }
    import json

    return {
        "model": "xiaomi.scales.ms116",
        "createTime": create_ms,
        "did": "blt.3.1abcdefabcd00",
        "fromSource": 3,
        "data": json.dumps(
            {
                "weight": weight,
                "bmi": "20.8",
                "heartRate": 72,
                "time": str(create_ms),
                "user": {"name": "Alice", "height": 174},
                "bodyResData": json.dumps(body),
            },
            ensure_ascii=False,
        ),
    }


class ParserTest(unittest.TestCase):
    def test_s800_source3(self):
        measurement = parse_record(s800_item())
        self.assertIsNotNone(measurement)
        assert measurement is not None
        self.assertEqual(measurement.weight_kg, 63.15)
        self.assertEqual(measurement.bmi, 20.8)
        self.assertEqual(measurement.body_fat_pct, 16.5)
        self.assertEqual(measurement.body_water_pct, 61.8)
        self.assertEqual(measurement.bone_mass_kg, 2.9)
        self.assertEqual(measurement.metabolic_age, 35)
        self.assertEqual(measurement.muscle_mass_kg, 49.8)
        self.assertEqual(measurement.protein_mass_kg, 10.3)
        self.assertEqual(measurement.visceral_fat, 4)
        self.assertEqual(measurement.basal_metabolism_kcal, 1508)
        self.assertEqual(measurement.body_score, 79)
        self.assertEqual(measurement.heart_rate_bpm, 72)
        self.assertEqual(measurement.skeletal_muscle_mass_kg, 28.6)
        self.assertEqual(measurement.physique_rating, 4)
        self.assertEqual(measurement.height_cm, 174)
        self.assertEqual(measurement.user, "Alice")
        self.assertEqual(measurement.source, "blt.3.1abcdefabcd00")
        self.assertEqual(measurement.extras["ram"], "2.7")
        self.assertEqual(measurement.to_row(full=True)["right_arm_muscle_kg"], "2.7")
        self.assertEqual(measurement.to_dict(full=True)["extras"]["ram"], "2.7")

    def test_source1(self):
        import json

        item = {
            "model": "yunmai.scales.ms103",
            "createTime": 1700000000000,
            "fromSource": 1,
            "data": json.dumps(
                {
                    "weight": 70.5,
                    "bmi": 22.1,
                    "bfp": 18.0,
                    "bwp": 55.0,
                    "bmc": 3.0,
                    "ma": 30,
                    "slm": 52.0,
                    "pm": 12.0,
                    "vfl": 5,
                    "bmr": 1600,
                    "sbc": 80,
                    "heartRate": 68,
                    "smm": 30.0,
                    "bt": 3,
                    "reportFrom": "Regular",
                    "user": {"name": "Bob", "height": "180"},
                }
            ),
        }
        measurement = parse_record(item)
        assert measurement is not None
        self.assertEqual(measurement.weight_kg, 70.5)
        self.assertEqual(measurement.user, "Bob")
        self.assertEqual(measurement.source, "Regular")
        self.assertEqual(measurement.height_cm, 180)

    def test_skips_non_weight_records(self):
        self.assertIsNone(parse_record({"createTime": 1700000000000, "data": "{}"}))

    def test_dedupe_keeps_richest(self):
        poor = s800_item(body_fat="")
        rich = s800_item(body_fat="16.5")
        result = dedupe_measurements(parse_records([poor, rich]))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].body_fat_pct, 16.5)

    def test_dedupe_does_not_merge_different_users(self):
        first = s800_item()
        second = s800_item()
        import json

        data = json.loads(second["data"])
        data["user"]["name"] = "Bob"
        second["data"] = json.dumps(data)
        result = dedupe_measurements(parse_records([first, second]))
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
