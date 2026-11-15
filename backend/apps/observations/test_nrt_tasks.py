import csv
import hashlib
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from apps.observations.tasks import acquire_firms_nrt, prepare_gabon_import
from apps.observations.management.commands.import_firms import _row_to_observation
from apps.observations.models import (
    GridCellMonth, HotspotObservation, ImportBatch, ProcessingLevelChoices, SourceChoices,
)


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

    def test_explicit_sp_version_in_mixed_batch_stays_sp(self):
        row = {
            "latitude": "0.5", "longitude": "10.5", "acq_date": "2026-11-15",
            "acq_time": "1200", "satellite": "N20", "version": "2.0SP",
        }
        batch = ImportBatch(processing_level=ProcessingLevelChoices.NRT)
        self.assertFalse(_row_to_observation(row, batch, SourceChoices.VIIRS_NOAA20).is_nrt)

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


class NrtCountingTests(TestCase):
    def _import(self, root: Path, folder: str, filename: str, rows: list[str]) -> None:
        directory = root / folder
        directory.mkdir()
        (directory / filename).write_text(
            "latitude,longitude,acq_date,acq_time,satellite,instrument,version,frp,type\n"
            + "\n".join(rows) + "\n",
            encoding="utf-8",
        )
        call_command("import_firms", data_dir=str(directory), verbosity=0)

    def test_overlapping_windows_and_revised_version_count_once_preserving_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = "0.5,10.5,2026-11-15,1200,N20,VIIRS,2.0NRT,3.5,0"
            revised = "0.5000001,10.5000001,2026-11-15,1200,N20,VIIRS,2.1NRT,7.0,0"
            other = "0.6,10.6,2026-11-15,1200,N20,VIIRS,2.1NRT,2.0,0"
            sp = "0.5,10.5,2026-11-15,1200,N20,VIIRS,2.0SP,9.0,0"
            self._import(root, "window1", "viirs-noaa20_nrt_1.csv", [first])
            self._import(root, "window2", "viirs-noaa20_nrt_2.csv", [first, revised, other])
            self._import(root, "standard", "viirs-noaa20_sp.csv", [sp])

            self.assertEqual(ImportBatch.objects.count(), 3)
            self.assertEqual(HotspotObservation.objects.count(), 4)
            self.assertEqual(
                list(HotspotObservation.objects.filter(is_nrt=True).order_by("id").values_list("counts_in_aggregates", flat=True)),
                [False, False, True],
            )
            self.assertTrue(HotspotObservation.objects.get(is_nrt=False).counts_in_aggregates)
            cell = GridCellMonth.objects.get(filter_static=True)
            self.assertEqual(cell.viirs_noaa20_count, 2)
            self.assertAlmostEqual(cell.frp_sum_noaa20, 11.0)

            # A rebuild also repairs legacy rows that predate the counting rule.
            HotspotObservation.objects.filter(is_nrt=True).update(counts_in_aggregates=True)
            call_command("import_firms", rebuild_only=True, verbosity=0)
            self.assertEqual(
                HotspotObservation.objects.filter(is_nrt=True, counts_in_aggregates=False).count(), 2
            )
            self.assertEqual(GridCellMonth.objects.get(filter_static=True).viirs_noaa20_count, 2)

            call_command("import_firms", data_dir=str(root / "window2"), force=True, verbosity=0)
            self.assertEqual(ImportBatch.objects.count(), 3)
            self.assertEqual(HotspotObservation.objects.count(), 4)
            self.assertEqual(GridCellMonth.objects.get(filter_static=True).viirs_noaa20_count, 2)

            # A later rebuild restores the NRT canonical row when SP is removed.
            HotspotObservation.objects.filter(is_nrt=False).delete()
            call_command("import_firms", rebuild_only=True, verbosity=0)
            self.assertEqual(
                list(HotspotObservation.objects.filter(is_nrt=True).order_by("id").values_list("counts_in_aggregates", flat=True)),
                [True, False, True],
            )
            self.assertEqual(GridCellMonth.objects.get(filter_static=True).viirs_noaa20_count, 2)

    def test_sp_only_historical_group_is_not_recounted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._import(root, "standard", "viirs-noaa20_sp.csv", [
                "0.5,10.5,2024-08-01,1200,N20,VIIRS,2.0SP,3.5,0",
                "0.5,10.5,2024-08-01,1200,N20,VIIRS,3.0SP,4.5,0",
            ])
            self.assertEqual(HotspotObservation.objects.filter(counts_in_aggregates=True).count(), 2)
            self.assertEqual(GridCellMonth.objects.get(filter_static=True).viirs_noaa20_count, 2)
