import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from pipeline.firms_area_acquire import acquire


class Response:
    def __init__(self, content): self.content=content
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self,limit): return self.content[:limit]


class FirmsAreaTests(unittest.TestCase):
    def test_missing_type_and_secret_not_saved(self):
        key="x"*32
        body=b"latitude,longitude,acq_date,acq_time,satellite,instrument,version\n0,10,2026-11-07,30,N20,VIIRS,2.0NRT\n"
        with tempfile.TemporaryDirectory() as tmp, patch("urllib.request.urlopen",return_value=Response(body)):
            output=Path(tmp); result=acquire("VIIRS_NOAA20_NRT",date(2026,11,5),5,output,key)
            self.assertEqual(result["rows"],1); self.assertFalse(result["type_column_present"])
            self.assertEqual(result["observation_coverage"],"unknown")
            self.assertNotIn(key,json.dumps(result))
            with self.assertRaises(FileExistsError): acquire("VIIRS_NOAA20_NRT",date(2026,11,5),5,output,key)

    def test_rejects_response_outside_requested_period(self):
        body=b"latitude,longitude,acq_date,acq_time,satellite,instrument,version\n0,10,2026-11-14,30,N20,VIIRS,2NRT\n"
        with tempfile.TemporaryDirectory() as tmp, patch("urllib.request.urlopen",return_value=Response(body)):
            with self.assertRaisesRegex(ValueError,"outside requested"):
                acquire("VIIRS_NOAA20_NRT",date(2026,11,5),5,Path(tmp),"x"*32)
            self.assertFalse(list(Path(tmp).iterdir()))

    def test_rejects_coordinates_and_time(self):
        for row in (b'0,99,2026-11-07,30,N20,VIIRS,2NRT', b'0,10,2026-11-07,2460,N20,VIIRS,2NRT'):
            body=b'latitude,longitude,acq_date,acq_time,satellite,instrument,version\n'+row+b'\n'
            with self.subTest(row=row), tempfile.TemporaryDirectory() as tmp, patch('urllib.request.urlopen',return_value=Response(body)):
                with self.assertRaises(ValueError):
                    acquire('VIIRS_NOAA20_NRT',date(2026,11,5),5,Path(tmp),'x'*32)
                self.assertFalse(list(Path(tmp).iterdir()))


if __name__=="__main__": unittest.main()
