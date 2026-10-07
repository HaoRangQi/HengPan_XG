"""布林矩形：初始区间、中点一次复核、向前逐根扩展遇坏即停。"""
import unittest

import numpy as np

from api.hengpan.anchored_box import extract_series
from api.hengpan.scanner import evaluate_rule
from api.hengpan.tests.test_ma_flat import bars
from api.hengpan.router import HengpanRule, HengpanMatch
from api.crypto.hengpan_router import CryptoHengpanMatch


def run(prices, **changes):
    params = dict(box_type='boll_box', boll_period=20, boll_multiplier=2.,
                  min_box_bars=50, rectangle_tolerance=.2, **{})
    params.update(changes)
    return evaluate_rule(extract_series(bars(prices)), params)


def reference(prices, index, n=20, k=2):
    window = np.asarray(prices[index - n + 1:index + 1])
    return window.mean() + k * window.std(), window.mean() - k * window.std()


class EndpointBollTest(unittest.TestCase):
    def test_fifty_bars_with_twenty_warmup_use_the_correct_four_points(self):
        prices = 100 + np.sin(np.arange(70))
        result = run(prices, rectangle_tolerance=10)
        self.assertEqual(result.get('boll_geometry'), 'endpoints_v1')
        self.assertEqual(result['box_bars'], 50)
        hu, hl = reference(prices, 20)
        tu, tl = reference(prices, 69)
        self.assertAlmostEqual(result['head_upper'], hu)
        self.assertAlmostEqual(result['head_lower'], hl)
        self.assertAlmostEqual(result['tail_upper'], tu)
        self.assertAlmostEqual(result['tail_lower'], tl)
        self.assertEqual(result['lookback_start'], bars(prices).iloc[20]['date'])
        self.assertEqual(result['box_end'], bars(prices).iloc[-1]['date'])
        expected = max(abs(tu - hu), abs(tl - hl)) / ((hu - hl + tu - tl) / 2)
        self.assertAlmostEqual(result['rectangle_error'], expected)
        self.assertIsNone(run(prices[1:]))

    def test_initial_middle_excursion_rejects_aligned_endpoints(self):
        prices = 100 + np.tile([-1., 1.], 35)
        prices[30:45] += 50
        result = run(prices, rectangle_tolerance=0)
        self.assertFalse(result['passed_body'])
        self.assertFalse(result['passed_full'])
        self.assertEqual(result['box_bars'], 50)
        self.assertAlmostEqual(result['rectangle_error'], 0)
        self.assertGreater(result['actual_range'], .4)
        # 预热最老一根不属于首端 BOLL20 的 19 根前值，不应影响四点。
        prices[0] = 300
        self.assertEqual(run(prices, rectangle_tolerance=0)['head_upper'], result['head_upper'])

    def test_failed_minimum_cannot_be_rescued_by_a_longer_matching_box(self):
        prices = 100 + np.tile([-1., 1.], 60)
        prices[51:72] += 25
        # L=50 的头点为索引 70，均值明显偏离；L=100 的头点为索引 20，恰好对齐。
        self.assertGreater(reference(prices, 70)[0], reference(prices, 119)[0] + 20)
        result = run(prices, rectangle_tolerance=0)
        self.assertFalse(result['passed_body'])
        self.assertEqual(result['box_bars'], 50)
        self.assertFalse(result['history_limited'])

    def test_first_failed_extension_keeps_the_previous_head(self):
        prices = 100 + np.tile([-1., 1.], 60)
        prices[49] += 25
        # 初始头 70 与新头 69 都合格；头 68 的预热包含尖峰。
        # 更老的头 20 又与尾部对齐，但不能跳过 68 继续找。
        self.assertEqual(reference(prices, 20), reference(prices, 119))
        self.assertGreater(reference(prices, 68)[0], reference(prices, 119)[0])
        result = run(prices, rectangle_tolerance=0)
        self.assertTrue(result['passed_body'])
        self.assertEqual(result['box_bars'], 51)
        self.assertEqual(result['lookback_start'], bars(prices).iloc[69]['date'])
        self.assertEqual(result['head_upper'], reference(prices, 69)[0])
        self.assertFalse(result['history_limited'])

    def test_first_extension_can_fail_without_discarding_initial_box(self):
        prices = 100 + np.tile([-1., 1.], 60)
        prices[50] += 25
        result = run(prices, rectangle_tolerance=0)
        self.assertTrue(result['passed_body'])
        self.assertEqual(result['box_bars'], 50)
        self.assertFalse(result['history_limited'])

    def test_midpoint_is_not_checked_again_during_extension(self):
        prices = 100 + np.tile([-1., 1.], 100)
        prices[120] += 25
        # 初始 [100,199] 的中点 149 合格；扩展后中点会经过 120，
        # 但这时不能再次复核中点。所有候选头点 100..10 都合格。
        self.assertEqual(reference(prices, 149, n=10), reference(prices, 199, n=10))
        self.assertGreater(reference(prices, 120, n=10)[0], reference(prices, 199, n=10)[0])
        result = run(prices, boll_period=10, min_box_bars=100, rectangle_tolerance=0)
        self.assertTrue(result['passed_body'])
        self.assertEqual(result['box_bars'], 190)
        self.assertTrue(result['history_limited'])

    def test_left_and_right_half_must_each_pass(self):
        for head_shift, tail_shift in [(-.6, 0), (0, -.6)]:
            with self.subTest(head_shift=head_shift, tail_shift=tail_shift):
                prices = 100 + np.tile([-1., 1.], 35)
                prices[1:21] += head_shift
                prices[25:45] += .6
                prices[50:70] += tail_shift
                # 整体偏差 15%，一半偏差 15%，另一半偏差 30%。
                result = run(prices, rectangle_tolerance=.2)
                self.assertLess(result['rectangle_error'], .2)
                self.assertFalse(result['passed_body'])

    def test_initial_midpoint_uses_left_middle_for_even_lengths(self):
        for count in (50, 51):
            with self.subTest(count=count):
                prices = 100 + np.resize([-1., 1.], 20 + count)
                midpoint = (20 + len(prices) - 1) // 2
                # 恰好位于中点 BOLL20 的第一根；选成右侧相邻根会漏检。
                prices[midpoint - 19] += 25
                self.assertFalse(run(prices, min_box_bars=count)['passed_body'])

    def test_zero_width_at_initial_midpoint_is_rejected(self):
        prices = 100 + np.tile([-1., 1.], 35)
        prices[25:45] = 100
        self.assertFalse(run(prices, rectangle_tolerance=10)['passed_body'])

    def test_endpoint_tilt_or_width_change_fails(self):
        base = 100 + np.tile([-1., 1.], 35)
        for tail in (base[-20:] + 10, 100 + np.tile([-4., 4.], 10)):
            prices = base.copy()
            prices[-20:] = tail
            result = run(prices)
            self.assertFalse(result['passed_body'])
            self.assertGreater(result['rectangle_error'], .2)

    def test_legacy_rail_tolerances_do_not_override_the_new_checks(self):
        prices = 100 + np.tile([-1., 1.], 35)
        result = run(prices, rail_tolerance=0, bandwidth_tolerance=0)
        self.assertTrue(result['passed_body'])
        self.assertEqual(result['passed_body'], result['passed_full'])

    def test_closed_interval_length_and_rescaling(self):
        prices = 100 + np.tile([-1., 1.], 100)
        for scale in (1e-8, 1., 1e7):
            result = run(prices * scale, min_box_bars=30)
            self.assertEqual(result['box_bars'], 180)
            self.assertTrue(result['passed_body'])
            self.assertAlmostEqual(result['head_upper'] / scale, 102)
        self.assertTrue(run(prices[-50:], min_box_bars=30)['passed_body'])

    def test_flat_price_is_degenerate_and_not_a_rectangle(self):
        result = run(np.full(70, 100.))
        self.assertFalse(result['passed_body'])
        self.assertIsNone(result['rectangle_error'])

    def test_response_models_preserve_geometry_and_tolerance(self):
        result = run(100 + np.tile([-1., 1.], 35))
        for cls in (HengpanMatch, CryptoHengpanMatch):
            restored = cls(**result).model_dump()
            for key in ('boll_geometry', 'head_upper', 'head_lower', 'tail_upper', 'tail_lower',
                        'rectangle_error', 'box_end'):
                self.assertEqual(restored.get(key), result[key])
        rule = HengpanRule(box_type='boll_box', rectangle_tolerance=.15)
        self.assertEqual(rule.model_dump().get('rectangle_tolerance'), .15)


if __name__ == '__main__':
    unittest.main()
