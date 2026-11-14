import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from pipeline.compare_postgis_direct import compare


class DirectPostGISTests(unittest.TestCase):
    def test_country_mismatch_fails_before_model_evaluation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); calendar=root/"calendar.json"; manifest=root/"manifest.json"; direct=root/"direct.csv"
            calendar.write_text(json.dumps({"rows":[{"month":"2020-01","source":"modis","satellite":"Terra","count_raw":10}]}),encoding="utf-8")
            manifest.write_text(json.dumps({"calendar_sha256":hashlib.sha256(calendar.read_bytes()).hexdigest()}),encoding="utf-8")
            direct.write_text("month,source,satellite,country_count,ga_count\n2020-01,modis,Terra,9,8\n",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"does not match PostGIS"):
                compare(calendar,manifest,direct)


if __name__ == "__main__": unittest.main()
