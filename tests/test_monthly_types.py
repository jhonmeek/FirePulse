import tempfile
import unittest
from pathlib import Path
from pipeline.normalize import normalize
from pipeline.aggregate_monthly import aggregate
from pipeline.monthly_types import build


class MonthlyTypesTests(unittest.TestCase):
    def test_exclusive_counts_missing_year_and_checksum(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); raw=root/"raw"; raw.mkdir(); norm=root/"norm"; monthly=root/"monthly"
            header="latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight,type\n"
            row="0,10,300,1,1,2020-01-01,0,Terra,MODIS,50,6.1,290,2,D,"
            (raw/"modis_2020_Gabon.csv").write_text(header+row+"0\n"+row+"2\n",encoding="utf-8")
            normalize(raw,norm); aggregate(norm,monthly)
            result=build(norm,monthly/"calendar.json",monthly/"manifest.json")
            jan=next(r for r in result["rows"] if r["month"]=="2020-01" and r["satellite"]=="Terra")
            self.assertEqual(jan["type_counts"],{"0":1,"1":0,"2":1,"3":0,"unavailable":0})
            missing=next(r for r in result["rows"] if r["month"]=="2019-01" and r["satellite"]=="Terra")
            self.assertEqual(missing["status"],"missing_input")
            self.assertTrue(all(v is None for v in missing["type_counts"].values()))
            (norm/"modis_2020_Gabon_normalized.csv").write_text("modified",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"checksum"):
                build(norm,monthly/"calendar.json",monthly/"manifest.json")


if __name__=="__main__": unittest.main()
