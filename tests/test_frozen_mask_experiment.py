"""Check that future observations never influence the frozen mask."""
import unittest
from pipeline.frozen_mask_experiment import build_mask


class FrozenMaskTests(unittest.TestCase):
    def test_future_type23_detections_do_not_trigger_mask(self):
        base={"latitude":"-0.01", "longitude":"10.01", "source":"modis", "hotspot_type":"2"}
        training=[{**base,"acquired_at":"2016-12-01T00:00:00Z"} for _ in range(19)]
        future=[{**base,"acquired_at":"2017-01-01T00:00:00Z"} for _ in range(50)]
        self.assertEqual(build_mask(training+future), set())
        training.append({**base,"acquired_at":"2016-12-31T00:00:00Z"})
        self.assertEqual(build_mask(training+future), {(-1,200)})


if __name__ == "__main__": unittest.main()
