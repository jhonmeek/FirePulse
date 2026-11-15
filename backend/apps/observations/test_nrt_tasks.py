import csv
import hashlib
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.test import SimpleTestCase

from apps.observations.tasks import acquire_firms_nrt, prepare_gabon_import
from apps.observations.management.commands.import_firms import _row_to_observation
from apps.observations.models import ImportBatch, ProcessingLevelChoices, SourceChoices


class NrtTaskTests(SimpleTestCase):
    def test_missing_firms_type_remains_unknown(self):
        row = {
            "latitude": "0.5", "longitude": "10.5", "acq_date": "2026-11-15",
            "acq_time": "1200", "satellite": "N20", "instrument": "VIIRS",
            "version": "2.0NRT", "confidence": "n", "frp": "3.5",
        }
        batch = ImportBatch(processing_level=ProcessingLevelChoices.NRT)
        observation = _row_to_observation(row, batch, SourceChoices.VIIRS_NOAA20)
        self.assertIsNone(observation.hotspot_type)
        self.assertTrue(observation.is_nrt)

    def test_disabled_task_does_not_access_firms(self):
        with patch.dict("os.environ", {"FIRMS_NRT_ENABLED": "false", "FIRMS_MAP_KEY": ""}):
            self.assertEqual(acquire_firms_nrt.apply().get(), {"status": "disabled"})

    def test_gabon_filter_preserves_raw_and_excludes_neighbors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "viirs_noaa20_nrt_2026-11-15_2026-11-15.csv"
            raw.write_text(
                "latitude,longitude,acq_date,acq_time,satellite,instrument,version\n"
                "0.5,10.5,2026-11-15,1200,N20,VIIRS,2.0NRT\n"
                "2,12,2026-11-15,1200,N20,VIIRS,2.0NRT\n",
                encoding="utf-8",
            )
            polygon = MultiPolygon(Polygon(((10, 0), (11, 0), (11, 1), (10, 1), (10, 0))))
            with patch("apps.observations.tasks.Region.objects.get", return_value=SimpleNamespace(geom=polygon)):
                imported, count = prepare_gabon_import(raw, root / "import")
            self.assertEqual(count, 1)
            self.assertTrue(imported.name.startswith("viirs-noaa20_nrt_"))
            with imported.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["latitude"], "0.5")
            self.assertEqual(len(raw.read_text(encoding="utf-8").splitlines()), 3)
            manifest = json.loads((root / "import" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_sha256"], hashlib.sha256(raw.read_bytes()).hexdigest())
            self.assertEqual(manifest["retained_within_ga"], 1)
