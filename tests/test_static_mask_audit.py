"""Tests for the M1 measurement of the current M2 static-cell rule."""
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.static_mask_audit import audit


class StaticMaskAuditTests(unittest.TestCase):
    def _input(self, root: Path, rows: list[dict]) -> Path:
        root.mkdir(parents=True)
        source = root / "sample_normalized.csv"
        fields = ["latitude", "longitude", "source", "hotspot_type", "acquired_at"]
        with source.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        manifest = {
            "schema_version": 1,
            "artifact_kind": "firepulse-normalized",
            "files": [{"output_file": source.name, "output_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}],
        }
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return root

    def test_type23_threshold_masks_cell_and_counts_type0_exposure(self):
        rows = [
            {"latitude": "-0.01", "longitude": "10.01", "source": "modis", "hotspot_type": "2", "acquired_at": "2020-01-01T00:00:00Z"}
            for _ in range(20)
        ]
        rows.append({"latitude": "-0.02", "longitude": "10.02", "source": "modis", "hotspot_type": "0", "acquired_at": "2020-02-01T00:00:00Z"})
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = audit(self._input(root / "in", rows), root / "out")
            self.assertEqual(result["flagged_cells"], 1)
            self.assertEqual(result["type0_in_flagged_cells"], 1)
            with (root / "out" / "static_mask_cells.csv").open(encoding="utf-8", newline="") as stream:
                cell = next(csv.DictReader(stream))
            self.assertEqual(cell["lat0"], "-0.05")  # SQL FLOOR, not truncation to zero.
            self.assertEqual(cell["reason"], "type23_threshold")

    def test_48_distinct_snpp_months_flags_cell(self):
        rows = [
            {"latitude": "0.11", "longitude": "10.11", "source": "viirs-snpp", "hotspot_type": "0", "acquired_at": f"{year}-{month:02d}-01T00:00:00Z"}
            for year in (2020, 2021, 2022, 2023) for month in range(1, 13)
        ]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = audit(self._input(root / "in", rows), root / "out")
            self.assertEqual(result["flagged_cells"], 1)
            self.assertEqual(result["type0_in_flagged_cells"], 48)
            self.assertEqual(result["detections_in_flagged_cells_by_source"], {"viirs-snpp": 48})

    def test_input_checksum_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            input_dir = self._input(root / "in", [])
            (input_dir / "sample_normalized.csv").write_text("changed\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                audit(input_dir, root / "out")


if __name__ == "__main__":
    unittest.main()
