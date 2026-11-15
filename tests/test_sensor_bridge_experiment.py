"""Check bridge direction, chronological separation and missing months."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from pipeline.sensor_bridge_experiment import experiment
from pipeline.temporal_experiment import month_range


class SensorBridgeTests(unittest.TestCase):
    def test_ratio_fit_is_not_changed_by_later_values(self):
        rows = []
        for month in month_range("2018-04", "2025-12"):
            for source, value in (("viirs-noaa20", 10), ("viirs-snpp", 20 if month <= "2019-12" else 40)):
                rows.append({"month": month, "source": source, "status": "observed_detections_recorded", "count_raw": value})
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); cal=root/"calendar.json"; manifest=root/"manifest.json"
            cal.write_text(json.dumps({"rows":rows}),encoding="utf-8")
            manifest.write_text(json.dumps({"calendar_sha256":hashlib.sha256(cal.read_bytes()).hexdigest()}),encoding="utf-8")
            result=experiment(cal,manifest)
            self.assertEqual(result["ratio"],2)
            self.assertEqual(result["eligible_months"],{"fit":21,"diagnostic":36,"evaluate":36})
            self.assertEqual(result["metrics"]["evaluate"]["mae"],20)
            self.assertEqual(result["metrics"]["evaluate"]["bias"],-20)


if __name__ == "__main__": unittest.main()
