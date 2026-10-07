import unittest
from unittest.mock import patch
import pandas as pd
from api.hengpan.fetcher import clean_kline
from api.analyzers.box_detector import check_box_pattern
from api.analyzers.combined_analyzer import analyze_stock
from api.analyzers.position_analyzer import analyze_position


def frame(n=60, freq='h'):
    return pd.DataFrame({'date': pd.date_range('2026-01-01', periods=n, freq=freq).astype(str),
                         'open': 10., 'high': 11., 'low': 9., 'close': 10., 'volume': 100.})


class ReliabilityTests(unittest.TestCase):
    def test_missing_st_is_unknown(self):
        self.assertIsNone(clean_kline(frame(), '60').iloc[-1]['isST'])

    def test_quality_threshold_is_the_only_score_gate(self):
        evidence = {'is_box_pattern': False, 'box_quality': .55, 'volatility': .01,
                    'support_levels': [9.], 'resistance_levels': [11.]}
        with patch('api.analyzers.box_detector.analyze_box_pattern', return_value=evidence):
            self.assertTrue(check_box_pattern(frame(), 30, .5)[0])
            self.assertFalse(check_box_pattern(frame(), 30, .6)[0])

    def test_passing_small_window_not_vetoed_by_large_window(self):
        evidence = {'platform_windows': [20], 'details': {20: {'box_analysis': {'is_box_pattern': True, 'box_quality': .55}}, 60: {}},
                    'selection_reasons': {20: 'pass'}}
        with patch('api.analyzers.combined_analyzer.analyze_enhanced_platform', return_value=evidence), \
             patch('api.analyzers.combined_analyzer.analyze_box_pattern', return_value={'is_box_pattern': False}):
            result = analyze_stock(frame(), [20, 60], use_low_position=False)
        self.assertTrue(result['is_platform'])
        self.assertIn(20, result['details'])

    def test_position_period_is_calendar_days(self):
        data = frame(60)
        data.loc[0, 'high'] = 20.
        self.assertTrue(analyze_position(data, 60, 3, .3)['is_low_position'])

    def test_position_requires_requested_lookback(self):
        self.assertFalse(analyze_position(frame(), 365, 180, 0)['is_low_position'])

    def test_quality_preparation_rejects_stale_and_only_gapped_windows(self):
        from api.data_quality import prepare_scan_frame
        data = frame()
        prepared, windows, reason = prepare_scan_frame(data, [20, 60], '1h', '2026-01-03')
        self.assertEqual(windows, [20, 60])
        self.assertIsNone(reason)
        _, windows, reason = prepare_scan_frame(data, [20], '1h', '2026-01-04')
        self.assertEqual(reason, 'stale')
        data = data.drop(index=10).reset_index(drop=True)
        _, windows, reason = prepare_scan_frame(data, [20, 59], '1h', '2026-01-03')
        self.assertEqual(windows, [20])
        self.assertIsNone(reason)

    def test_unknown_st_survives_scan_item(self):
        from api.hengpan.scanner import build_item
        data = frame()
        data['amount'], data['turn'], data['isST'] = 1000., 1., None
        item = build_item({'code': 'sh.600000', 'name': 'demo', 'industry': 'demo'}, data, {}, '2026-01-03')
        self.assertIsNone(item['is_st'])

    def test_quality_is_not_rounded_before_comparison(self):
        evidence = {'is_box_pattern': True, 'box_quality': .549, 'volatility': .01,
                    'support_levels': [9.], 'resistance_levels': [11.]}
        with patch('api.analyzers.box_detector.analyze_box_pattern', return_value=evidence):
            self.assertFalse(check_box_pattern(frame(), 30, .55)[0])

    def test_full_timestamp_anchor_rejects_earlier_hour(self):
        from api.data_quality import prepare_scan_frame
        data = frame()
        anchor = str(pd.Timestamp(data['date'].iloc[-1]) + pd.Timedelta(hours=1))
        self.assertEqual(prepare_scan_frame(data, [20], '1h', anchor)[2], 'stale')

    def test_unclosed_candle_is_excluded(self):
        from api.data_quality import prepare_scan_frame
        data = frame()
        previous = data['date'].iloc[-2]
        now = pd.Timestamp(data['date'].iloc[-1]) + pd.Timedelta(minutes=30)
        result, windows, reason = prepare_scan_frame(data, [20], '1h', previous, now=now)
        self.assertEqual(len(result), 59)
        self.assertEqual(windows, [20])
        self.assertIsNone(reason)

    def test_intraday_stock_gap_excludes_long_window(self):
        from api.data_quality import prepare_scan_frame
        data = frame(12)
        data['date'] = [f'2026-01-{day:02d} {hour}' for day in (5, 6, 7)
                        for hour in ('10:30:00', '11:30:00', '14:00:00', '15:00:00')]
        data = data.drop(index=3).reset_index(drop=True)
        _, windows, reason = prepare_scan_frame(data, [4, 11], '60', '2026-01-07', ['2026-01-05', '2026-01-06', '2026-01-07'])
        self.assertEqual(windows, [4])
        self.assertIsNone(reason)

    def test_crypto_all_401_matches_are_retained(self):
        from api.crypto.hengpan_scan import scan_hengpan, new_stats
        symbols = [{'symbol': f'COIN{i}', 'category': 'perpetual'} for i in range(401)]
        rules = [{'id': '1', 'params': {'lookback': 20}}]
        frames = {item['symbol']: frame() for item in symbols}
        stats = new_stats('2026-01-03', rules)
        streamed = []
        with patch('api.crypto.hengpan_scan.latest_scan_timestamp', return_value='2026-01-03'), \
             patch('api.crypto.hengpan_scan.load_frames', return_value=frames), \
             patch('api.crypto.hengpan_scan.analyze_symbol', side_effect=lambda info, *args: {'symbol': info['symbol']}):
            found = scan_hengpan(None, symbols, rules, '2026-01-03', stats, on_found=streamed.append)
        self.assertEqual(len(found), 401)
        self.assertEqual(len(streamed), 401)
        self.assertEqual(stats['truncated'], 0)

    def test_online_default_anchor_resolves_trading_day_once(self):
        from concurrent.futures import ThreadPoolExecutor
        from api.config import ScanConfig
        from api.platform_scanner import scan_stocks
        data = frame(40, 'D')
        anchor = data['date'].iloc[-1][:10]
        config = ScanConfig(windows=[20], use_low_position=False, use_volume_analysis=False,
                            use_box_detection=False, expected_count=None, max_workers=1)
        with patch('api.hengpan.fetcher.resolve_scan_date', return_value=anchor) as resolve, \
             patch('api.platform_scanner.ProcessPoolExecutor', ThreadPoolExecutor), \
             patch('api.platform_scanner.baostock_login'), \
             patch('api.platform_scanner.fetch_kline_data', return_value=data):
            found = scan_stocks([{'code': 'sh.600000', 'name': 'demo'}], config)
        resolve.assert_called_once()
        self.assertEqual(len(found), 1)

    def test_stock_all_401_matches_are_retained(self):
        from concurrent.futures import ThreadPoolExecutor
        from api.hengpan.scanner import scan_anchored_box, new_stats
        stocks = [{'code': f'sh.{600000 + i}', 'name': 'demo'} for i in range(401)]
        rules = [{'id': '1', 'params': {'lookback': 20}}]
        stats = new_stats('2026-01-03', rules)
        streamed = []
        with patch('api.hengpan.scanner.ProcessPoolExecutor', ThreadPoolExecutor), \
             patch('api.hengpan.scanner._init_worker'), \
             patch('api.hengpan.scanner.fetch_kline', return_value=frame()), \
             patch('api.hengpan.scanner.analyze_stock', side_effect=lambda info, *args, **kwargs: {'code': info['code']}):
            found = scan_anchored_box(stocks, rules, {'max_workers': 2, 'retry_attempts': 1},
                                     '2026-01-03', stats, frequency='d', on_found=streamed.append)
        self.assertEqual(len(found), 401)
        self.assertEqual(len(streamed), 401)
        self.assertEqual(stats['truncated'], 0)
