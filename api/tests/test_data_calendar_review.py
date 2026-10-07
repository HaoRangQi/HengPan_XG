"""Regression checks for elapsed-time and trading-calendar integration."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from api.analyzers.decline_analyzer import analyze_decline_speed
from api.config import ScanConfig
from api.platform_scanner import scan_stocks
from api.store import db


class CalendarReviewTests(unittest.TestCase):
    def test_decline_elapsed_days_do_not_round_down(self):
        data = pd.DataFrame({'date': pd.date_range('2026-01-05 10:00', periods=100, freq='h').astype(str),
                             'open': 10., 'high': 10., 'low': 10., 'close': 10.})
        data.loc[0, 'high'] = 20.
        data.loc[95, 'low'] = 8.
        result = analyze_decline_speed(data, 100, 3, .3, 30, .15)
        self.assertFalse(result['details']['decline_period_satisfied'])
        self.assertFalse(result['is_low_position'])

    def test_online_daily_uses_available_calendar_and_preserves_weekend(self):
        calendar = pd.bdate_range('2026-01-05', periods=40).strftime('%Y-%m-%d').tolist()
        data = pd.DataFrame({'date': calendar, 'open': 10., 'high': 10.1, 'low': 9.9,
                             'close': 10., 'volume': 100.})
        config = ScanConfig(windows=[30], use_low_position=False, use_volume_analysis=False,
                            use_box_detection=False, expected_count=None, max_workers=1)
        with tempfile.TemporaryDirectory() as temporary:
            database = str(Path(temporary) / 'market.db')
            with db.open_db(database) as conn:
                conn.executemany('INSERT INTO trade_calendar(calendar_date,is_trading_day) VALUES (?,?)',
                                 [(day, '1') for day in calendar])
                conn.commit()
            with patch.object(db, 'DB_PATH', database), \
                 patch('api.platform_scanner.ProcessPoolExecutor', ThreadPoolExecutor), \
                 patch('api.platform_scanner.baostock_login'), redirect_stdout(io.StringIO()):
                with patch('api.platform_scanner.fetch_kline_data', return_value=data):
                    complete = scan_stocks([{'code': 'sh.600000', 'name': 'Example'}], config,
                                           end_date=calendar[-1])
                with patch('api.platform_scanner.fetch_kline_data', return_value=data.drop(index=20)):
                    suspended = scan_stocks([{'code': 'sh.600000', 'name': 'Example'}], config,
                                            end_date=calendar[-1])
        self.assertEqual(len(complete), 1)
        self.assertEqual(suspended, [])
