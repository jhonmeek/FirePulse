"""End-to-end test of classify_hotspots on synthetic rasters and FIRMS rows (needs GDAL)."""

import csv
import gzip
import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path


def _gdal_available():
    try:
        from django.contrib.gis.gdal.libgdal import gdal_version
        gdal_version()
        return True
    except Exception:
        return False


@unittest.skipUnless(_gdal_available(), "GDAL/GeoDjango not available")
class ClassifyHotspotsCommandTests(unittest.TestCase):
    def test_end_to_end_report(self):
        from django.contrib.gis.gdal import GDALRaster
        from django.core.management import call_command

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lc_dir, firms_dir = root / "lc", root / "firms"
            lc_dir.mkdir(); firms_dir.mkdir()
            # 200x200 px, 0.01 deg, lon 9..11, lat 1..-1: west forest (2), east savanna (9), 20 px of sea (17) on the west edge
            # plus a 20x20 px savanna/cropland checkerboard (alternating columns) around lat 0, lon 10.5
            data = []
            for row in range(200):
                line = [17] * 20 + [2] * 80 + [9] * 100
                if 90 <= row < 110:
                    for col in range(140, 160):
                        line[col] = 9 if col % 2 == 0 else 12
                data += line
            GDALRaster({"driver": "GTiff", "name": str(lc_dir / "lc_2018.tif"), "srid": 4326, "width": 200,
                        "height": 200, "origin": [9.0, 1.0], "scale": [0.01, -0.01], "datatype": 1,
                        "bands": [{"data": data, "nodata_value": 255}]})
            (lc_dir / "manifest.json").write_text("{}", encoding="utf-8")
            boundary = root / "boundary.geojson"
            boundary.write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {},
                "geometry": {"type": "Polygon", "coordinates": [[[9.3, -0.8], [10.8, -0.8], [10.8, 0.8], [9.3, 0.8], [9.3, -0.8]]]}}]}),
                encoding="utf-8")
            header = "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight,type\n"
            rows = ["0.0,9.5,320,1,1,2018-07-10,0930,Terra,MODIS,80,6.1,290,10,D,0",   # forest
                    "0.5,10.5,320,1,1,2018-07-11,0930,Terra,MODIS,80,6.1,290,10,D,0",  # savanna
                    "0.5,10.6,320,1,1,2018-08-11,0930,Terra,MODIS,80,6.1,290,10,D,0",  # savanna
                    "0.0,9.1,320,1,1,2018-01-11,0930,Terra,MODIS,80,6.1,290,10,D,3",   # offshore on sea
                    "0.0,10.505,320,1,1,2018-02-11,0930,Terra,MODIS,80,6.1,290,10,D,0"]  # checkerboard -> mixed
            (firms_dir / "modis_2018_Gabon.csv").write_text(header + "\n".join(rows) + "\n", encoding="utf-8")
            output = root / "out" / "report.json"
            detections = root / "out" / "detections.csv.gz"
            call_command("classify_hotspots", firms_dir=str(firms_dir), land_cover_dir=str(lc_dir),
                         boundary=str(boundary), output=str(output), detections_output=str(detections),
                         area_samples=500, stdout=StringIO())

            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["detections"], 5)
            modis = report["by_source"]["modis"]
            self.assertEqual(modis["landscape"], {"savanna": 2, "tropical_forest": 1, "not_applicable": 1, "mixed": 1})
            self.assertEqual(report["vegetation_fires_inferred"]["by_source_count"]["modis"], {"savanna": 2, "tropical_forest": 1})
            self.assertEqual(report["thermal_type_vs_land_cover"]["offshore_or_water"], {"water": 1})
            self.assertEqual(report["outside_gabon_boundary"], {"offshore_or_water": 1})
            area = report["land_area_share_gabon"]["mean_share"]
            self.assertAlmostEqual(area["savanna"], 0.53, delta=0.08)  # 0.8/1.5 of the boundary width
            self.assertGreater(report["enrichment_fire_share_over_area_share"]["modis"]["savanna"], 1)
            with gzip.open(detections, "rt", encoding="utf-8") as stream:
                lines = list(csv.DictReader(stream))
            self.assertEqual(len(lines), 5)
            self.assertEqual(lines[4]["status"], "indeterminate")
            with self.assertRaises(Exception):  # refuses to overwrite
                call_command("classify_hotspots", firms_dir=str(firms_dir), land_cover_dir=str(lc_dir),
                             boundary=str(boundary), output=str(output), detections_output=str(root / "x.csv.gz"),
                             area_samples=10, stdout=StringIO())


if __name__ == "__main__":
    unittest.main()
