import tempfile
import unittest
from pathlib import Path
from pipeline.nrt_ingest import prepare


class NrtIngestTests(unittest.TestCase):
    def test_2026_missing_type_is_explicitly_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/"source.csv"
            source.write_text("latitude,longitude,acq_date,acq_time,version\n0,10,2026-01-01,30,2NRT\n",encoding="utf-8")
            result=prepare(source,"VIIRS_NOAA20_NRT")
            self.assertEqual(result["monthly_type_counts"],[{"month":"2026-01","type_nasa":"unavailable","detection_count":1}])
            self.assertFalse(result["source_product_verified"])

    def test_rejects_wrong_year_and_invalid_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/"source.csv"
            source.write_text("latitude,longitude,acq_date,acq_time,version,type\n0,10,2025-01-01,30,2NRT,0\n",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"2026"): prepare(source,"VIIRS_NOAA20_NRT")
            source.write_text("latitude,longitude,acq_date,acq_time,version,type\n0,10,2026-01-01,30,2NRT,9\n",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"preflight"): prepare(source,"VIIRS_NOAA20_NRT")


if __name__ == "__main__": unittest.main()
