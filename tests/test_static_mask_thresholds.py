"""Exercise the M1 audit at the documented candidate-mask boundaries."""
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.static_mask_audit import audit


class StaticMaskThresholds(unittest.TestCase):
    def test_thresholds_are_inclusive_and_months_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, out = root / 'normalized', root / 'audit'
            source.mkdir()
            file = source / 'sample.csv'
            fields = ['latitude', 'longitude', 'hotspot_type', 'source', 'acquired_at']
            rows = []
            def add(lat, kind, source_name, timestamp):
                rows.append(dict(zip(fields, [lat, 10, kind, source_name, timestamp])))
            for _ in range(19): add(0.01, '2', 'modis', '2020-01-01')
            for _ in range(20): add(0.11, '3', 'modis', '2020-01-01')
            for i in range(47): add(0.21, '0', 'viirs-snpp', f'{2012+i//12:04d}-{i%12+1:02d}-01')
            for i in range(48): add(-0.01, '0', 'viirs-snpp', f'{2012+i//12:04d}-{i%12+1:02d}-01')
            for _ in range(10): add(0.21, '0', 'viirs-snpp', '2012-01-10')
            with file.open('w', encoding='utf-8', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
            digest = hashlib.sha256(file.read_bytes()).hexdigest()
            (source / 'manifest.json').write_text(json.dumps({'artifact_kind':'firepulse-normalized','schema_version':1,'files':[{'output_file':file.name,'output_sha256':digest}]}), encoding='utf-8')
            result = audit(source, out)
            with (out / 'static_mask_cells.csv').open(encoding='utf-8', newline='') as stream:
                cells = list(csv.DictReader(stream))
            self.assertEqual(result['flagged_cells'], 2)
            self.assertEqual({(row['lat0'], row['reason']) for row in cells}, {('0.10','type23_threshold'), ('-0.05','snpp_persistence')})
            self.assertEqual(next(row for row in cells if row['lat0'] == '-0.05')['active_months_snpp'], '48')


if __name__ == '__main__': unittest.main()
