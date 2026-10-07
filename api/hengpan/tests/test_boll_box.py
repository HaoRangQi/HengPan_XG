"""布林矩形：滚动轨道、动态尾部和双市场契约。"""
import unittest
from unittest.mock import patch

import numpy as np
from pydantic import ValidationError

from api.hengpan import scanner
from api.hengpan.anchored_box import extract_series
from api.hengpan.router import HengpanRule, HengpanMatch, _rule_key, validate_rules
from api.crypto import hengpan_scan
from api.crypto.hengpan_router import CryptoHengpanMatch, CryptoHengpanScanRequest
from api.history.store import rule_keys
from api.hengpan.tests.test_ma_flat import bars


def wave(count, period=30, scale=1):
    return (100 + 2 * np.sin(np.arange(count) * 2 * np.pi / period)) * scale


def params(**changes):
    return {**HengpanRule().model_dump(), 'box_type': 'boll_box', 'boll_period': 30,
            'boll_multiplier': 2., 'min_box_bars': 80, 'rectangle_tolerance': .2, **changes}


def check(prices, **changes):
    return scanner.evaluate_rule(extract_series(bars(prices)), params(**changes))


class BollAlgorithmTest(unittest.TestCase):
    def test_defaults_do_not_reuse_legacy_rail_tolerances(self):
        from api.hengpan import boll_box
        self.assertEqual(boll_box.RECTANGLE_TOLERANCE, .2)
        self.assertEqual(boll_box.RULE_FIELDS, ('boll_period', 'boll_multiplier', 'min_box_bars', 'rectangle_tolerance'))

    def test_registered(self):
        self.assertIn('boll_box', scanner.RULE_EVALUATORS)

    def test_rectangle_has_dynamic_length_and_real_rolling_bands(self):
        result = check(wave(400))
        self.assertTrue(result['passed_body'])
        self.assertEqual(result['box_bars'], 370)
        self.assertTrue(result['history_limited'])
        self.assertAlmostEqual(result['upper'], 100 + 2 * np.sqrt(2), places=8)
        self.assertAlmostEqual(result['lower'], 100 - 2 * np.sqrt(2), places=8)
        self.assertLess(result['rectangle_error'], 1e-8)

    def test_warmup_and_minimum_are_independent(self):
        self.assertIsNone(check(wave(109)))
        self.assertEqual(check(wave(110))['box_bars'], 80)
        self.assertTrue(check(wave(110))['passed_body'])
        self.assertIsNone(check(wave(119), min_box_bars=90))
        self.assertEqual(check(wave(500, 20), boll_period=20)['box_bars'], 480)
        self.assertEqual(check(wave(60), min_box_bars=30)['box_bars'], 30)

    def test_wide_and_tiny_price_rectangles_are_not_silently_filtered(self):
        for scale in (1e-8, 1., 1e6):
            result = check(wave(200, scale=scale))
            self.assertEqual(result['box_bars'], 170)
            self.assertTrue(result['passed_body'])
        self.assertTrue(check(100 + 30 * np.sin(np.arange(200) * 2 * np.pi / 30))['passed_body'])

    def test_linear_trend_does_not_align_at_any_candidate_length(self):
        self.assertFalse(check(100 + np.arange(240) * .3)['passed_body'])

    def test_extension_stops_when_a_candidate_head_reaches_a_price_spike(self):
        prices = wave(280)
        prices[140] = 160
        result = check(prices)
        self.assertTrue(result['passed_body'])
        # BOLL30 在索引 170 后才不包含索引 140 的尖峰。
        self.assertEqual(result['box_bars'], 110)
        self.assertFalse(result['history_limited'])

    def test_zero_width_and_invalid_prices_are_not_rectangles(self):
        result = check(np.full(200, 100.))
        self.assertFalse(result['passed_body'])
        for bad in (0., -1., float('nan'), float('inf')):
            prices = wave(150)
            prices[-20] = bad
            self.assertIsNone(check(prices))
        prices = wave(200)
        prices[10] = float('nan')
        result = check(prices)
        self.assertTrue(result['passed_body'])
        self.assertEqual(result['box_bars'], 159)

    def test_zero_volume_is_a_boundary_not_a_flat_market(self):
        frame = bars(wave(200))
        frame.loc[150, 'volume'] = 0
        result = scanner.evaluate_rule(extract_series(frame), params())
        self.assertIsNone(result)

    def test_last_breakout_is_not_absorbed_into_reference_bands(self):
        prices = wave(159)
        prices[-1] = 105
        result = check(prices, rectangle_tolerance=1.)
        self.assertTrue(result['passed_body'])
        self.assertEqual(result['tail_state'], 'above')
        self.assertEqual(result['tail_bars'], 1)
        self.assertEqual(result['passed_full'], result['passed_body'])


class BollContractTest(unittest.TestCase):
    def test_both_markets_apply_initial_checks_and_first_failure_boundary(self):
        midpoint_bad = 100 + np.tile([-1., 1.], 35)
        midpoint_bad[30:45] += 50
        minimum_bad = 100 + np.tile([-1., 1.], 60)
        minimum_bad[51:72] += 25
        extension_bad = 100 + np.tile([-1., 1.], 60)
        extension_bad[49] += 25
        midpoint_once = 100 + np.tile([-1., 1.], 100)
        midpoint_once[120] += 25
        cases = [('midpoint', midpoint_bad, 20, 50, None),
                 ('minimum', minimum_bad, 20, 50, None),
                 ('extension', extension_bad, 20, 50, 51),
                 ('midpoint_once', midpoint_once, 10, 100, 190)]
        for name, prices, period, minimum, expected_bars in cases:
            with self.subTest(name=name):
                frame = bars(prices)
                rules = [{'id': '1', 'params': params(boll_period=period,
                         min_box_bars=minimum, rectangle_tolerance=0)}]
                a_stats = scanner.new_stats('2026-09-28', rules)
                u_stats = hengpan_scan.new_stats('2026-09-28', rules)
                a = scanner.analyze_stock({'code': 'sh.600000', 'name': '测试', 'industry': '测试'},
                                          frame, rules, '2026-09-28', a_stats)
                u = hengpan_scan.analyze_symbol({'symbol': 'TESTUSDT', 'category': 'perpetual'},
                                                frame, rules, '2026-09-28', u_stats)
                for item, stats in [(a, a_stats), (u, u_stats)]:
                    self.assertEqual(stats['rules']['1']['analyzed'], 1)
                    self.assertEqual(stats['rules']['1']['passed_body'], int(expected_bars is not None))
                    if expected_bars is None:
                        self.assertIsNone(item)
                    else:
                        match = item['matches']['1']
                        self.assertEqual(match['box_bars'], expected_bars)
                        self.assertEqual(match['lookback_start'], frame.iloc[-expected_bars]['date'])
                        self.assertAlmostEqual(match['avg_amount'], frame.iloc[-expected_bars:]['amount'].mean())
                if expected_bars is not None:
                    self.assertAlmostEqual(u['matches']['1']['avg_trades'],
                                           frame.iloc[-expected_bars:]['number_of_trades'].mean())

    def test_defaults_validation_and_both_responses(self):
        rule = CryptoHengpanScanRequest(rules=[{'box_type': 'boll_box'}]).rules[0]
        self.assertEqual(rule.boll_period, 30)
        self.assertEqual(rule.min_box_bars, 80)
        for key, value in [('boll_period', 1), ('boll_period', 20.5), ('min_box_bars', 29),
                           ('boll_multiplier', 0), ('rail_tolerance', float('nan')),
                           ('rectangle_tolerance', -1), ('rectangle_tolerance', float('inf'))]:
            with self.subTest(key=key), self.assertRaises(ValidationError):
                HengpanRule(**params(**{key: value}))
        # 下限即观察起点 30 根；默认仍是 80，可按需下调。
        self.assertEqual(HengpanRule(**params(min_box_bars=30)).min_box_bars, 30)
        result = check(wave(180))
        for cls in (HengpanMatch, CryptoHengpanMatch):
            restored = cls(**result).model_dump()
            for key in ('box_bars', 'boll_period', 'boll_multiplier', 'rectangle_error',
                        'head_upper', 'head_lower', 'tail_upper', 'tail_lower', 'box_end', 'bandwidth', 'history_limited', 'boll_start'):
                self.assertEqual(restored[key], result[key])

    def test_active_fields_only_define_rule_identity(self):
        rule = params()
        other = params(lookback=10, max_breach=20, ma_period=70)
        self.assertEqual(_rule_key(rule), _rule_key(other))
        self.assertEqual(len(validate_rules([other])), 1)
        def key(p):
            return rule_keys({'kind': 'hengpan_a', 'frequency': '60',
                              'rules': [{'id': '1', 'params': p}]}, {'matched_rules': ['1']})
        self.assertEqual(key(rule), key(other))
        for name, value in [('boll_period', 20), ('boll_multiplier', 3), ('min_box_bars', 100),
                            ('rectangle_tolerance', .3)]:
            self.assertNotEqual(_rule_key(rule), _rule_key(params(**{name: value})))
            self.assertNotEqual(key(rule), key(params(**{name: value})))

    def test_both_scanners_and_crypto_unlimited_history(self):
        frame = bars(wave(800))
        rules = [{'id': '1', 'params': params()}]
        a = scanner.analyze_stock({'code': 'sh.600000', 'name': '测试', 'industry': '测试'},
                                  frame, rules, '2026-09-28', scanner.new_stats('2026-09-28', rules))
        stats = hengpan_scan.new_stats('2026-09-28', rules)
        with patch.object(hengpan_scan, 'load_frames', return_value={'TESTUSDT': frame}) as load, \
                patch.object(hengpan_scan, "latest_scan_timestamp", return_value="2026-09-28"):
            items = hengpan_scan.scan_hengpan(None, [{'symbol': 'TESTUSDT', 'category': 'perpetual'}],
                                              rules, '2026-09-28', stats)
        self.assertIsNone(load.call_args.args[2])
        self.assertEqual(a['matches']['1']['box_bars'], 770)
        self.assertEqual(items[0]['matches']['1']['box_bars'], 770)
        self.assertAlmostEqual(items[0]['matches']['1']['avg_trades'], frame.iloc[30:]['number_of_trades'].mean())

    def test_history_round_trip_keeps_every_rectangle_metric(self):
        import os
        import tempfile
        from api.history import db as history_db, store as history_store
        match = HengpanMatch(**check(wave(200))).model_dump()
        snapshot = {'scan_date': '2026-09-28', 'frequency': '60', 'status': 'completed',
                    'params': {'markets': ['sh_main']},
                    'rules': [{'id': '1', 'params': params()}],
                    'stats': {'rules': {'1': {'passed_full': 1}}},
                    'results': [{'code': 'sh.600000', 'name': '样本', 'industry': '测试',
                                 'is_st': False, 'date': '2026-09-28 15:00:00', 'close': 100.,
                                 'amplitude': .002, 'matches': {'1': match},
                                 'kline_data': [{'date': '2026-09-28 15:00:00', 'close': 100.}]}]}
        with tempfile.TemporaryDirectory() as temp:
            conn = history_db.connect(os.path.join(temp, 'history.db'))
            self.addCleanup(conn.close)
            history_store.save_run('hengpan_a', 'boll-run', snapshot, conn=conn,
                                   kline_base_dir=os.path.join(temp, 'kline'))
            payload = history_store.get_run('boll-run', conn=conn)
        restored = payload['results'][0]['matches']['1']
        for key in ('mode', 'box_bars', 'boll_period', 'boll_multiplier', 'rectangle_error',
                    'head_upper', 'head_lower', 'tail_upper', 'tail_lower', 'box_end', 'bandwidth', 'boll_start', 'lookback_start',
                    'history_limited', 'upper', 'lower', 'tail_state'):
            self.assertEqual(restored[key], match[key], key)
        self.assertEqual(payload['rules'][0]['params']['min_box_bars'], 80)

    def test_gap_and_unclosed_bar_are_excluded(self):
        frame = bars(wave(220)).drop(index=40).reset_index(drop=True)
        rules = [{'id': '1', 'params': params()}]
        stats = hengpan_scan.new_stats('2026-09-28', rules)
        result = hengpan_scan.analyze_symbol({'symbol': 'TESTUSDT', 'category': 'perpetual'},
                                             frame, rules, '2026-09-28', stats)
        self.assertEqual(result['matches']['1']['box_bars'], 149)


if __name__ == '__main__':
    unittest.main()
