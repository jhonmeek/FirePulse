"""Exercise the enabled NRT path without making a network request to FIRMS."""

import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.test import TestCase

from apps.api.cache import get_data_epoch
from apps.observations.models import GridCellMonth, HotspotObservation, ImportBatch, Region
from apps.observations.tasks import acquire_firms_nrt


class EnabledNrtTaskTests(TestCase):
    def setUp(self):
        Region.objects.create(
            code="GA",
            name="Gabon",
            geom=MultiPolygon(Polygon.from_bbox((10, 0, 11, 1))),
            bbox_json=[10, 0, 11, 1],
        )

    def test_acquisition_imports_only_ga_and_invalidates_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original_exists = Path.exists
            lock = Mock()
            lock.acquire.return_value = True
            redis = Mock()
            redis.lock.return_value = lock

            def fake_acquisition(args, **kwargs):
                output = Path(args[args.index("--output-dir") + 1])
                csv_path = output / "viirs_noaa20_nrt_sample.csv"
                csv_path.write_text(
                    "latitude,longitude,acq_date,acq_time,satellite,instrument,version,confidence,frp\n"
                    "0.5,10.5,2026-11-15,1200,N20,VIIRS,2.0NRT,n,3.5\n"
                    "2,12,2026-11-15,1200,N20,VIIRS,2.0NRT,n,4.5\n",
                    encoding="utf-8",
                )
                (output / "sample.manifest.json").write_text(
                    json.dumps({
                        "csv_file": csv_path.name,
                        "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
                        "product": "VIIRS_NOAA20_NRT",
                    }),
                    encoding="utf-8",
                )
                return Mock(returncode=0)

            with (
                patch.dict("os.environ", {
                    "FIRMS_NRT_ENABLED": "true",
                    "FIRMS_MAP_KEY": "test-only-placeholder",
                    "FIRMS_NRT_DIR": str(root),
                }),
                patch("apps.observations.tasks.Redis.from_url", return_value=redis),
                patch("apps.observations.tasks.subprocess.run", side_effect=fake_acquisition),
                patch(
                    "apps.observations.tasks.Path.exists",
                    autospec=True,
                    side_effect=lambda path: True if str(path) == "/pipeline/firms_area_acquire.py" else original_exists(path),
                ),
                patch("apps.api.cache._EPOCH_FILE", root / "epoch"),
            ):
                before = get_data_epoch()
                result = acquire_firms_nrt.apply(throw=True).get()
                after = get_data_epoch()

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["gabon_rows"], 1)
            self.assertEqual(HotspotObservation.objects.count(), 1)
            self.assertEqual(ImportBatch.objects.count(), 1)
            self.assertEqual(GridCellMonth.objects.filter(filter_static=False).count(), 1)
            self.assertNotEqual(before, after)
            lock.release.assert_called_once()

            output = next(path for path in root.iterdir() if path.is_dir())
            manifest = json.loads((output / "import" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["retained_within_ga"], 1)
