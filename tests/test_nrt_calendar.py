import json
import tempfile
import unittest
from pathlib import Path
from pipeline.nrt_calendar import build


class NrtCalendarTests(unittest.TestCase):
    def test_partial_month_and_missing_month_are_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"observations.json"
            item={"acquired_at":"2026-11-14T00:41:00Z","source_line":2,"type_nasa":None}
            path.write_text(json.dumps({"artifact_kind":"firepulse-nrt-observations","schema_version":1,"observation_count":1,"observations":[item]}),encoding="utf-8")
            rows=build(path)["rows"]
            self.assertIsNone(rows[0]["detection_count"])
            self.assertEqual(rows[0]["status"],"not_in_extract")
            self.assertEqual(rows[10]["detection_count"],1)
            self.assertEqual(rows[10]["type_counts"],{"unavailable":1})
            self.assertEqual(rows[10]["status"],"partial_nrt_extract")
            self.assertEqual(rows[10]["observation_coverage"],"unknown")

    def test_duplicate_source_line_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"observations.json"; item={"acquired_at":"2026-11-14T00:41:00Z","source_line":2,"type_nasa":None}
            path.write_text(json.dumps({"artifact_kind":"firepulse-nrt-observations","schema_version":1,"observation_count":2,"observations":[item,item]}),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"duplicate source line"): build(path)


if __name__ == "__main__": unittest.main()
