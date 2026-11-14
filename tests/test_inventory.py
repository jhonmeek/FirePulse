import tempfile
import unittest
from pathlib import Path

from pipeline.inventory import audit


BASE = "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,daynight,type"
MODIS = BASE + ",brightness,bright_t31,scan,track,frp"
VIIRS = BASE + ",bright_ti4,bright_ti5,scan,track,frp"


class InventoryTests(unittest.TestCase):
    def make(self, root, name, text):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_input_must_exist_and_contain_csv(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(ValueError):
                audit(root / "missing", root / "out")
            (root / "empty").mkdir()
            with self.assertRaises(ValueError):
                audit(root / "empty", root / "out")

    def test_product_schemas_domains_duplicates_and_determinism(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / "raw"; out = root / "out"
            modis_row = "0,0,2020-01-01,0,Terra,MODIS,42,6.1,N,0,300,280,1,1,2"
            self.make(source, "modis_2020_Gabon.csv", MODIS + "\n" + modis_row + "\n" + modis_row + "\n")
            self.make(source, "modis_2021_Gabon.csv", MODIS + "\n" + modis_row + "\n")
            viirs_row = "nan,0,2021-02-01,5,Suomi-NPP,VIIRS,h,2,N,2,300,280,1,1,2"
            self.make(source, "viirs-snpp_2021_Gabon.csv", VIIRS + "\n" + viirs_row + "\n" + viirs_row.replace(",h,", ",42,") + "\n")
            self.make(source, "viirs-jpss1_2021_Gabon.csv", BASE + "\n")
            first_manifest, first_quality = audit(source, out)
            first = [(p.name, p.read_bytes()) for p in sorted(out.iterdir())]
            audit(source, out)
            self.assertEqual(first, [(p.name, p.read_bytes()) for p in sorted(out.iterdir())])
            reports = {r["file"]: r for r in first_quality["files_detail"]}
            self.assertEqual(reports["modis_2020_Gabon.csv"]["duplicate_exact_rows"], 1)
            self.assertEqual(reports["modis_2020_Gabon.csv"]["duplicate_exact_rows_inter_file_inclusive"], 2)
            self.assertEqual(first_quality["duplicate_exact_signatures_across_files"], 1)
            self.assertEqual(reports["viirs-snpp_2021_Gabon.csv"]["invalid_confidence"], 1)
            self.assertEqual(reports["modis_2020_Gabon.csv"]["invalid_confidence"], 0)
            self.assertEqual(reports["viirs-snpp_2021_Gabon.csv"]["nonfinite_numeric"], 2)
            self.assertIn("bright_ti4", reports["viirs-jpss1_2021_Gabon.csv"]["schema_missing_columns"])
            self.assertNotIn("brightness", reports["viirs-jpss1_2021_Gabon.csv"]["schema_missing_columns"])
            self.assertEqual(reports["viirs-snpp_2021_Gabon.csv"]["unpadded_times"], 2)
            self.assertEqual(reports["viirs-snpp_2021_Gabon.csv"]["filename_date_year_mismatch"], 0)
            self.assertEqual(first_manifest["file_count"], 4)
            self.assertTrue(all(v["status"] == "unknown" for v in first_quality["missing_months"].values()))
            with self.assertRaises(ValueError):
                audit(source, source / "nested")

    def test_irregular_csv_and_read_error_are_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / "raw"
            self.make(source, "modis_2020_Gabon.csv", MODIS + "\n0,0,2021-01-01,12000,T,MODIS,101,1,D,4,1,1,1,1,1,extra\n")
            _, quality = audit(source, root / "out")
            report = quality["files_detail"][0]
            self.assertEqual(report["malformed_rows"], 1)
            self.assertEqual(report["filename_date_year_mismatch"], 1)
            self.assertEqual(report["invalid_times"], 1)
            self.assertEqual(report["invalid_confidence"], 1)
            self.assertIsNone(report["read_error"])
            self.assertEqual(quality["read_errors"], 0)

    def test_decode_error_is_visible(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / "raw"
            path = self.make(source, "modis_2020_Gabon.csv", MODIS + "\n")
            path.write_bytes(path.read_bytes() + b"\xff\xfe\n")
            _, quality = audit(source, root / "out")
            report = quality["files_detail"][0]
            self.assertIn("UnicodeDecodeError", report["read_error"])
            self.assertEqual(quality["read_errors"], 1)


if __name__ == "__main__":
    unittest.main()
