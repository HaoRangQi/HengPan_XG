"""箱体宽度不设置业务范围上限，A 股和币圈共用同一契约。"""
import unittest
from pydantic import ValidationError
from api.hengpan.router import HengpanScanRequest, HengpanRule, validate_rules
from api.crypto.hengpan_router import CryptoHengpanScanRequest


class BoxWidthTest(unittest.TestCase):
    def test_custom_width_survives_both_request_models_and_rule_validation(self):
        for model in (HengpanScanRequest, CryptoHengpanScanRequest):
            for mode in ('fixed', 'tolerant'):
                for width in (0, 0.00000001, 0.001, 0.0049, 0.31125, 1.5, 10):
                    with self.subTest(model=model.__name__, mode=mode, width=width):
                        request = model(rules=[{'box_type': mode, 'box_height': width}])
                        rules = validate_rules(request.model_dump()['rules'])
                        self.assertEqual(rules[0]['params']['box_height'], width)

    def test_negative_and_non_finite_width_are_invalid_numbers(self):
        for width in (-1, float('inf'), float('-inf'), float('nan')):
            with self.subTest(width=width), self.assertRaises(ValidationError):
                HengpanRule(box_height=width)
