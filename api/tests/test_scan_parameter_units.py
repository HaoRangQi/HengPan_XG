import unittest
from pydantic import ValidationError
from api.config import ScanConfig,merge_config
from api.index import ScanConfigRequest
from api.crypto.platform_router import CryptoPlatformScanRequest

class UnitsTest(unittest.TestCase):
    def test_public_aliases_and_legacy_inputs(self):
        for cls in (ScanConfig,ScanConfigRequest):
            self.assertEqual(cls(high_point_lookback_bars=121).high_point_lookback_days,121)
            self.assertEqual(cls(high_point_lookback_days=122).high_point_lookback_days,122)
            with self.assertRaises(ValidationError):cls(high_point_lookback_bars=121,high_point_lookback_days=122)
        self.assertEqual(CryptoPlatformScanRequest(breakthrough_confirmation_bars=4).breakthrough_confirmation_days,4)
    def test_merge_preserves_new_bar_values(self):
        self.assertEqual(merge_config({'rapid_decline_bars':17}).rapid_decline_days,17)
