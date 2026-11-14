"""Checks the monthly 0.25-degree M1 grid and static-mask columns."""
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.grid_025 import build_grid


class Grid025Tests(unittest.TestCase):
    def test_counts_reconcile_and_mask_is_visible_without_deleting_raw(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_dir = root / "normalized"
            mask_dir = root / "mask"
            source_dir.mkdir()
            mask_dir.mkdir()
            fields = ["latitude", "longitude", "source", "satellite", "acquired_at", "hotspot_type"]
            rows = [
                {"latitude": "0.01", "longitude": "10.01", "source": "modis", "satellite": "Terra", "acquired_at": "2020-01-02T00:00:00Z", "hotspot_type": "0"},
                {"latitude": "0.02", "longitude": "10.02", "source": "modis", "satellite": "Terra", "acquired_at": "2020-01-03T00:00:00Z", "hotspot_type": "2"},
                {"latitude": "0.30", "longitude": "10.30", "source": "viirs-snpp", "satellite": "N", "acquired_at": "2020-01-04T00:00:00Z", "hotspot_type": "0"},
            ]
            data_path = source_dir / "sample.csv"
            with data_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            (source_dir / "manifest.json").write_text(json.dumps({"schema_version": 1, "artifact_kind": "firepulse-normalized", "files": [{"output_file": data_path.name, "output_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest()}]}), encoding="utf-8")
            (mask_dir / "static_mask_audit.json").write_text(json.dumps({"artifact_kind": "firepulse-static-mask-audit"}), encoding="utf-8")
            with (mask_dir / "static_mask_cells.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["lat0", "lon0"], lineterminator="\n")
                writer.writeheader()
                writer.writerow({"lat0": "0.00", "lon0": "10.00"})
            result = build_grid(source_dir, mask_dir, root / "grid")
            self.assertEqual(result["input_rows"], 3)
            self.assertEqual(result["grid_month_rows"], 2)
            with (root / "grid" / "grid_025_monthly.csv").open(encoding="utf-8", newline="") as stream:
                output = list(csv.DictReader(stream))
            terra = next(row for row in output if row["satellite"] == "Terra")
            self.assertEqual(terra["count_raw"], "2")
            self.assertEqual(terra["count_type0"], "1")
            self.assertEqual(terra["count_type0_unmasked"], "0")
            self.assertEqual(terra["count_in_static_mask"], "2")
            self.assertEqual(sum(int(row["count_raw"]) for row in output), 3)


if __name__ == "__main__":
    unittest.main()
