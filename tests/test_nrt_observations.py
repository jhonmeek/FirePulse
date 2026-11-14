import tempfile
import unittest
from pathlib import Path
from pipeline.nrt_observations import prepare


class NrtObservationTests(unittest.TestCase):
    def test_missing_type_preserves_original_and_utc(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/"input.csv"
            source.write_text("latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,daynight,frp\n0,10,2026-11-14,41,N20,VIIRS,n,2.0NRT,N,1.2\n",encoding="utf-8")
            result=prepare(source,"VIIRS_NOAA20_NRT"); item=result["observations"][0]
            self.assertIsNone(item["type_nasa"])
            self.assertEqual(item["type_status"],"unavailable")
            self.assertEqual(item["acquired_at"],"2026-11-14T00:41:00Z")
            self.assertEqual(item["source_line"],2)
            self.assertEqual(item["original_fields"]["frp"],"1.2")
            self.assertFalse(result["source_product_verified"])

    def test_rejects_bad_type_and_nonfinite_frp(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/"input.csv"
            head="latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,daynight,frp,type\n"
            source.write_text(head+"0,10,2026-11-14,41,N20,VIIRS,n,2.0NRT,N,1,9\n",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"invalid type"): prepare(source,"VIIRS_NOAA20_NRT")
            source.write_text(head+"0,10,2026-11-14,41,N20,VIIRS,n,2.0NRT,N,nan,0\n",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"invalid frp"): prepare(source,"VIIRS_NOAA20_NRT")


if __name__ == "__main__": unittest.main()
