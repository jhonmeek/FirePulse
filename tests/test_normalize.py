import csv, tempfile, unittest
from pathlib import Path
from pipeline.normalize import normalize, normalize_row

class NormalizeTests(unittest.TestCase):
    def test_datetime_confidence_source_and_hash_stability(self):
        row={"acq_date":"2020-01-02","acq_time":"5","latitude":"0","longitude":"10","instrument":"VIIRS","satellite":"N20","confidence":"h","version":"2.0NRT","bright_ti4":"300","bright_ti5":"290","scan":"1","track":"2","frp":"3","type":"0","daynight":"N"}
        a=normalize_row(row,"viirs-jpss1","viirs-jpss1_2020_Gabon.csv",2,"a"*64); b=normalize_row(row,"viirs-jpss1","viirs-jpss1_2020_Gabon.csv",2,"a"*64)
        self.assertEqual(a,b); self.assertEqual(a["source"],"viirs-noaa20"); self.assertEqual(a["acquired_at"],"2020-01-02T00:05:00Z"); self.assertEqual(a["confidence_tier"],"high"); self.assertEqual(a["is_nrt"],"true")
    def test_bounds_and_nonfinite_rejected(self):
        for x in ("91","NaN","Infinity"):
            row={"acq_date":"2020-01-01","acq_time":"0000","latitude":x,"longitude":"0","satellite":"Terra","instrument":"MODIS","confidence":"50","version":"1","type":"0","daynight":"D"}
            with self.assertRaises(ValueError): normalize_row(row,"modis","modis_2020_Gabon.csv",2,"h")
    def test_preserves_rows_duplicates_and_input(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=root/"in";src.mkdir(); out=root/"normalized"
            header="latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight,type\n"
            row="0,10,300,1,2,2020-01-01,5,Terra,MODIS,50,1,290,2,D,0\n"
            p=src/"modis_2020_Gabon.csv";p.write_text(header+row+row); original=p.read_bytes()
            metrics=normalize(src,out); self.assertEqual(metrics["rows"],2); self.assertEqual(p.read_bytes(),original)
            with (out/"modis_2020_Gabon_normalized.csv").open() as f: self.assertEqual(len(list(csv.DictReader(f))),2)
            self.assertEqual(metrics["duplicate_exact_rows"],1)
    def test_invalid_input_and_unknown_output_are_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);src=root/"in";src.mkdir();out=root/"out";out.mkdir();marker=out/"keep.txt";marker.write_text("user data")
            (src/"unexpected.csv").write_text("not,a,product\n")
            with self.assertRaises(ValueError): normalize(src,out)
            self.assertEqual(marker.read_text(),"user data")
    def test_required_categories_and_filename_year_fail(self):
        row={"acq_date":"2021-01-01","acq_time":"0","latitude":"0","longitude":"0","satellite":"Terra","instrument":"MODIS","confidence":"50","version":"1","type":"0","daynight":"D"}
        for field,value in (("daynight",""),("type","4"),("confidence","NaN")):
            bad=dict(row);bad[field]=value
            with self.assertRaises(ValueError): normalize_row(bad,"modis","modis_2021_Gabon.csv",2,"x")
        with self.assertRaises(ValueError): normalize_row(row,"modis","modis_2020_Gabon.csv",2,"x")
