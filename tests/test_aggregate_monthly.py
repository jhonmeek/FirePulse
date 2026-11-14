import csv,json,tempfile,unittest
from pathlib import Path
from pipeline.normalize import normalize
from pipeline.aggregate_monthly import aggregate

class AggregateTests(unittest.TestCase):
    def test_zero_absence_type0_and_reconciliation(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);src=root/"raw";src.mkdir(); n=root/"norm"; out=root/"monthly"
            header="latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight,type\n"
            (src/"modis_2020_Gabon.csv").write_text(header+"0,10,300,1,2,2020-01-01,0,Terra,MODIS,40,1,290,2,D,0\n"+"0,10,300,1,2,2020-03-01,0,Terra,MODIS,40,1,290,2,D,1\n")
            viirs="latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight,type\n"
            (src/"viirs-snpp_2012_Gabon.csv").write_text(viirs+"0,10,300,1,2,2012-01-20,5,N,VIIRS,n,1,290,2,D,0\n")
            (src/"viirs-jpss1_2020_Gabon.csv").write_text(viirs+"0,10,300,1,2,2020-01-20,5,N20,VIIRS,n,2,290,2,D,0\n")
            normalize(src,n); m=aggregate(n,out); self.assertEqual(m["source_rows"],4)
            with (out/"monthly_counts.csv").open() as f: rows=list(csv.DictReader(f))
            jan=next(r for r in rows if r["month"]=="2020-01" and r["satellite"]=="Terra"); feb=next(r for r in rows if r["month"]=="2020-02" and r["satellite"]=="Terra")
            self.assertEqual(jan["count_raw"],"1");self.assertEqual(jan["count_type0_candidate"],"1");self.assertEqual(feb["count_raw"],"0");self.assertEqual(feb["status"],"no_detections_recorded");self.assertEqual(feb["observation_coverage"],"unknown")
            s_jan=next(r for r in rows if r["month"]=="2012-01" and r["source"]=="viirs-snpp"); self.assertEqual(s_jan["status"],"partial_period"); self.assertEqual(s_jan["count_raw"],"1")
            n20=next(r for r in rows if r["month"]=="2020-01" and r["source"]=="viirs-noaa20"); self.assertEqual(n20["count_raw"],"1")
            self.assertEqual(next(r for r in rows if r["month"]=="2000-11" and r["source"]=="modis" and r["satellite"]=="Terra")["status"],"missing_input")
            self.assertEqual(next(r for r in rows if r["month"]=="2001-01" and r["source"]=="modis" and r["satellite"]=="Aqua")["status"],"not_available")
            cal=json.loads((out/"calendar.json").read_text()); records=cal["rows"]
            self.assertIsInstance(next(r for r in records if r["month"]=="2020-01" and r["source"]=="viirs-noaa20")["count_raw"],int)
            self.assertEqual(next(r for r in records if r["month"]=="2020-01" and r["source"]=="viirs-noaa20")["satellite"],"N20")
            self.assertIsNone(next(r for r in records if r["month"]=="2000-11" and r["source"]=="viirs-noaa20")["count_raw"])
            self.assertIsNone(records[0]["harmonized_value"])
            self.assertEqual(sum(r["count_raw"] or 0 for r in records),m["source_rows"])
            manifest_path=n/"manifest.json"; saved=manifest_path.read_text()
            bad=json.loads(saved);bad["files"][0]["output_sha256"]="0"*64;manifest_path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError): aggregate(n,out)
            manifest_path.write_text(saved)
            missing=n/json.loads(saved)["files"][0]["output_file"];payload=missing.read_bytes();missing.unlink()
            with self.assertRaises(ValueError): aggregate(n,out)
            missing.write_bytes(payload)
