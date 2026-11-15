import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from pipeline.postgis_frozen_experiment import experiment
from pipeline.temporal_experiment import month_range


class PostgisFrozenTests(unittest.TestCase):
    def test_type0_reconciliation_and_same_months(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); cal=root/"cal.json"; manifest=root/"manifest.json"; data=root/"sql.csv"
            rows=[]; sql=[]
            for i,month in enumerate(month_range("2012-02","2025-12")):
                for source,satellite in (("modis","Terra"),("modis","Aqua"),("viirs-snpp","N")):
                    n=10+i%12
                    rows.append({"month":month,"source":source,"satellite":satellite,"status":"observed_detections_recorded","count_raw":n+2})
                    sql.append({"month":month,"source":source,"satellite":satellite,"raw_count":n+2,"type0_count":n,"type0_unmasked_count":n-1,"type0_masked_count":1})
            cal.write_text(json.dumps({"rows":rows}),encoding="utf-8")
            manifest.write_text(json.dumps({"calendar_sha256":hashlib.sha256(cal.read_bytes()).hexdigest()}),encoding="utf-8")
            with data.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=sql[0].keys());w.writeheader();w.writerows(sql)
            result=experiment(cal,manifest,data)
            self.assertEqual(result["variants"]["type0_with_mask"]["eligible_months"],result["variants"]["type0_without_mask"]["eligible_months"])
            sql[0]["type0_masked_count"]=3
            with data.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=sql[0].keys());w.writeheader();w.writerows(sql)
            with self.assertRaisesRegex(ValueError,"reconciliation"):
                experiment(cal,manifest,data)


if __name__=="__main__": unittest.main()
