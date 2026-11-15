"""Contract tests for the maritime snapshot using a synthetic EEZ."""
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline import maritime_snapshot

try:
    import shapely  # noqa: F401
except ImportError:
    shapely = None


@unittest.skipIf(shapely is None, "Shapely is an optional dependency")
class MaritimeSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root / "source.csv"
        self.manifest = root / "manifest.json"
        self.boundary = root / "boundary.geojson"
        self.output = root / "output.geojson"
        rows = [
            (1, 1, "2026-01-01"),  # interior
            (0, 1, "2026-01-02"),  # edge
            (0, 0, "2026-01-02"),  # vertex
            (3, 1, "2026-01-02"),  # exterior
        ]
        with self.source.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["longitude", "latitude", "acq_date", "acq_time", "satellite", "instrument", "frp", "type"])
            writer.writerows([(*row, "1200", "N20", "VIIRS", "4.2", "0") for row in rows])
        boundary = {"type": "FeatureCollection", "features": [{
            "type": "Feature", "properties": {"mrgid": 8476},
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]},
        }]}
        self.boundary.write_text(json.dumps(boundary), encoding="utf-8")
        self.data = {
            "csv_sha256": hashlib.sha256(self.source.read_bytes()).hexdigest(),
            "product": "VIIRS_NOAA20_NRT", "requested_start": "2026-01-01",
            "requested_end": "2026-01-02", "requested_bbox": [-1, -1, 3, 3], "rows": 4,
            "retrieved_at_utc": "2026-01-03T00:00:00Z", "type_column_present": True,
        }
        self.write_manifest()

    def write_manifest(self):
        self.manifest.write_text(json.dumps(self.data), encoding="utf-8")

    def build(self):
        return maritime_snapshot.build(self.source, self.manifest, self.boundary, self.output)

    def test_valid_checksum_and_strict_boundary_exclusion(self):
        self.assertEqual(self.build(), 1)
        result = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual([feature["geometry"]["coordinates"] for feature in result["features"]], [[1.0, 1.0]])
        self.assertEqual(result["metadata"]["count"], 1)
        self.assertEqual(result["metadata"]["source_csv_sha256"], hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(result["metadata"]["boundary_sha256"], hashlib.sha256(self.boundary.read_bytes()).hexdigest())
        self.assertEqual(result["metadata"]["boundary_predicate"], "strictly within")

    def test_modified_csv_rejects_manifest_checksum(self):
        with self.source.open("a", encoding="utf-8") as stream:
            stream.write("\n")
        with self.assertRaisesRegex(ValueError, "manifest"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_wrong_satellite_is_rejected_even_with_valid_checksum(self):
        self.source.write_text(self.source.read_text(encoding="utf-8").replace("N20", "N21"), encoding="utf-8")
        self.data["csv_sha256"] = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "Satellite or instrument"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_missing_or_invalid_time_and_frp_are_rejected(self):
        original = self.source.read_text(encoding="utf-8")
        for replacement in (",,N20,VIIRS,4.2,", ",2460,N20,VIIRS,4.2,", ",1200,N20,VIIRS,nan,", ",1200,N20,VIIRS,abc,"):
            with self.subTest(replacement=replacement):
                self.source.write_text(original.replace(",1200,N20,VIIRS,4.2,", replacement), encoding="utf-8")
                self.data["csv_sha256"] = hashlib.sha256(self.source.read_bytes()).hexdigest()
                self.write_manifest()
                with self.assertRaises(ValueError):
                    self.build()
                self.assertFalse(self.output.exists())

    def test_short_time_and_numeric_frp_are_normalized(self):
        original = self.source.read_text(encoding="utf-8").replace(",1200,N20,", ",43,N20,")
        self.source.write_text(original, encoding="utf-8")
        self.data["csv_sha256"] = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.write_manifest()
        self.build()
        result = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(result["features"][0]["properties"]["acq_time_utc"], "0043")
        self.assertEqual(result["features"][0]["properties"]["frp"], 4.2)
        self.assertEqual(result["metadata"]["source_rows"], 4)

    def test_type_availability_reflects_only_retained_points(self):
        original = self.source.read_text(encoding="utf-8")
        original = original.replace("1,1,2026-01-01,1200,N20,VIIRS,4.2,0", "1,1,2026-01-01,1200,N20,VIIRS,4.2,")
        self.source.write_text(original, encoding="utf-8")
        self.data["csv_sha256"] = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.write_manifest()
        self.build()
        result = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertTrue(result["metadata"]["nasa_type_column_present"])
        self.assertFalse(result["metadata"]["nasa_type_available"])

    def test_bbox_must_cover_entire_boundary(self):
        self.data["requested_bbox"] = [0, 0, 1.99, 2]
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "bbox"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_manifest_rows_and_boundary_id_are_checked(self):
        self.data["rows"] = 999
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "Row count"):
            self.build()
        self.data["rows"] = 4
        self.write_manifest()
        obj = json.loads(self.boundary.read_text(encoding="utf-8"))
        obj["features"][0]["properties"]["mrgid"] = 1
        self.boundary.write_text(json.dumps(obj), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "MRGID"):
            self.build()

    def test_published_snapshot_matches_public_source_manifest(self):
        root = Path(__file__).resolve().parents[1]
        source = root / "data/fixtures/maritime/viirs_noaa20_nrt_2026-11-10_2026-11-14.csv"
        manifest = json.loads(source.with_suffix(".manifest.json").read_text(encoding="utf-8"))
        snapshot = json.loads((root / "front-bis/public/data/gabon-maritime-observations.geojson").read_text(encoding="utf-8"))
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), manifest["csv_sha256"])
        self.assertEqual(snapshot["metadata"]["source_csv_sha256"], manifest["csv_sha256"])
        self.assertEqual(snapshot["metadata"]["count"], len(snapshot["features"]))
        self.assertTrue(all(len(f["properties"]["acq_time_utc"]) == 4 for f in snapshot["features"]))
        self.assertEqual(snapshot["metadata"]["outside_or_boundary_rows"], manifest["rows"] - len(snapshot["features"]))
        with source.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        for feature in snapshot["features"]:
            lon, lat = feature["geometry"]["coordinates"]
            props = feature["properties"]
            matches = [r for r in rows if float(r["longitude"]) == lon and float(r["latitude"]) == lat and r["acq_date"] == props["acq_date"]]
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["acq_time"].zfill(4), props["acq_time_utc"])
            self.assertEqual(float(matches[0]["frp"]), props["frp"])

    def test_existing_output_is_never_overwritten(self):
        original = b"existing output\x00"
        self.output.write_bytes(original)
        with self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual(self.output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
