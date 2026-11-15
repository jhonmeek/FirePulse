"""A re-import must never delete an already imported batch or its observations."""

import tempfile
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from apps.observations.models import HotspotObservation, ImportBatch

HEADER = (
    "latitude,longitude,brightness,bright_t31,scan,track,acq_date,acq_time,"
    "satellite,confidence,version,frp,daynight,type\n"
)
ROW = "-0.50000,11.50000,330.10,290.20,1.0,1.0,2024-08-15,1010,Terra,80,6.1,12.3,D,0\n"
OTHER_ROW = "-0.40000,11.60000,331.10,291.20,1.0,1.0,2025-08-15,1010,Terra,80,6.1,13.3,D,0\n"


class ReimportProvenanceTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data_dir = Path(self.tmp.name)
        self.csv_path = self.data_dir / "modis_2024_Gabon.csv"
        self.csv_path.write_text(HEADER + ROW, encoding="utf-8")

    def _import(self, **options):
        call_command("import_firms", data_dir=str(self.data_dir), verbosity=0, **options)

    def test_forced_reimport_keeps_the_existing_batch_and_observations(self):
        self._import()
        batch = ImportBatch.objects.get()

        self._import(force=True)

        self.assertEqual(ImportBatch.objects.count(), 1)
        self.assertEqual(list(ImportBatch.objects.values_list("pk", flat=True)), [batch.pk])
        self.assertEqual(HotspotObservation.objects.count(), 1)

    def test_failed_import_of_a_new_file_keeps_existing_batches(self):
        self._import()
        batch = ImportBatch.objects.get()
        (self.data_dir / "modis_2025_Gabon.csv").write_text(
            HEADER + OTHER_ROW, encoding="utf-8"
        )

        target = "apps.observations.management.commands.import_firms._row_to_observation"
        with mock.patch(target, side_effect=RuntimeError("simulated parse failure")):
            with self.assertRaises(RuntimeError):
                self._import()

        self.assertTrue(ImportBatch.objects.filter(pk=batch.pk).exists())
        self.assertEqual(HotspotObservation.objects.count(), 1)
