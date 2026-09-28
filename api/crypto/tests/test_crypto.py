"""
加密行情库的回归测试。不联网：Binance 接口全部用假客户端替代，
返回的数据结构按研究文档第 3 节（K 线是 12 个元素的数组、价格是字符串）构造。
在项目根目录运行：api/.venv/bin/python -m unittest api.crypto.tests.test_crypto -v
"""
import io
import json
import os
import tempfile
import unittest
import urllib.error
from email.message import Message
from unittest.mock import patch

from api.crypto import binance, db, sync
from api.crypto.reader import load_kline
from api.store import db as store_db

HOUR = 3_600_000
# 2026-09-27 03:06 UTC，研究文档实测「末端 K 线未走完」时的请求时刻
AT = 1_790_478_360_000 - (1_790_478_360_000 % HOUR) + 6 * 60_000


def bar(open_time, price=100.0):
    """按文档格式构造一根 K 线：价格和成交量是字符串，时间和笔数是整数。"""
    p = f"{price:.2f}"
    return [open_time, p, f"{price + 1:.2f}", f"{price - 1:.2f}", p, "12.5",
            open_time + HOUR - 1, "1250.00", 42, "6.0", "600.00", "0"]


def symbol_def(symbol, contract_type="PERPETUAL", status="TRADING", quote="USDT"):
    return {"symbol": symbol, "pair": symbol, "contractType": contract_type,
            "deliveryDate": 4133404800000, "onboardDate": 1569398400000, "status": status,
            "maintMarginPercent": "2.5000", "requiredMarginPercent": "5.0000",
            "baseAsset": symbol.replace("USDT", ""), "quoteAsset": quote, "marginAsset": quote,
            "pricePrecision": 2, "quantityPrecision": 3, "baseAssetPrecision": 8,
            "quotePrecision": 8, "underlyingType": "COIN", "underlyingSubType": ["PoW"],
            "settlePlan": 0, "triggerProtect": "0.0500", "liquidationFee": "0.012500",
            "marketTakeBound": "0.05",
            "filters": [{"filterType": "PRICE_FILTER", "tickSize": "0.10"}],
            "orderTypes": ["LIMIT", "MARKET"], "timeInForce": ["GTC", "IOC"],
            "someFutureField": "接口以后新增的字段"}


class FakeClient:
    """模拟 BinanceClient：K 线从 listed_from 开始每小时一根，到 end_time 为止。"""

    def __init__(self, symbols=None, tickers=None, listed_from=None, fail=None):
        self.symbols = symbols or []
        self.tickers = tickers or []
        self.listed_from = listed_from or {}
        self.fail = fail or {}
        self.requests = 0
        self.used_weight = 0
        self.kline_calls = []

    def exchange_info(self):
        self.requests += 1
        return {"symbols": self.symbols}

    def ticker_24hr(self):
        self.requests += 1
        return self.tickers

    def klines(self, symbol, interval, start_time=None, end_time=None, limit=1500):
        self.requests += 1
        self.kline_calls.append((symbol, start_time, end_time, limit))
        if symbol in self.fail:
            raise self.fail[symbol]
        first = max(start_time, self.listed_from.get(symbol, 0))
        first = -(-first // HOUR) * HOUR
        out, t = [], first
        while t + HOUR - 1 <= end_time and len(out) < limit:
            out.append(bar(t))
            t += HOUR
        return out


class CryptoTestCase(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        os.unlink(self.path)
        self.conn = db.connect(self.path)

    def tearDown(self):
        self.conn.close()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(self.path + suffix):
                os.unlink(self.path + suffix)

    def seed_pool(self, client):
        sync.sync_symbols(self.conn, client)
        sync.sync_ticker(self.conn, client)


# --------------------------------------------------------------------------

class SchemaTest(CryptoTestCase):
    def test_kline_columns_follow_documented_array_order(self):
        """12 个下标按官方文档命名、顺序不变，前面只多一列本地的 symbol。"""
        expected = ["symbol", "open_time", "open", "high", "low", "close", "volume",
                    "close_time", "quote_asset_volume", "number_of_trades",
                    "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"]
        for category in db.CATEGORIES:
            info = self.conn.execute(f"PRAGMA table_info({db.kline_table('1h', category)})").fetchall()
            self.assertEqual([r["name"] for r in info], expected)
            keyed = sorted((r["pk"], r["name"]) for r in info if r["pk"])
            self.assertEqual(keyed, [(1, "symbol"), (2, "open_time")])

    def test_ticker_columns_keep_interface_names(self):
        info = self.conn.execute("PRAGMA table_info(crypto_ticker_24hr)").fetchall()
        self.assertEqual([r["name"] for r in info], list(db.TICKER_FIELDS) + ["updated_at"])

    def test_tables_split_by_category_and_separate_from_a_share(self):
        names = {r[0] for r in self.conn.execute("SELECT name FROM sqlite_master")}
        self.assertTrue({"crypto_kline_1h_perpetual", "crypto_kline_1h_tradifi",
                         "crypto_kline_1h_all"} <= names)
        # 独立的库文件，不和 A 股的 market.db 混在一起
        self.assertNotEqual(os.path.abspath(db.DB_PATH), os.path.abspath(store_db.DB_PATH))
        self.assertTrue(db.DB_PATH.endswith("crypto.db"))

    def test_no_extra_indexes(self):
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL").fetchall()
        self.assertEqual(rows, [])


class SymbolSyncTest(CryptoTestCase):
    def client(self):
        return FakeClient(
            symbols=[symbol_def("BTCUSDT"), symbol_def("XAUUSDT", "TRADIFI_PERPETUAL"),
                     symbol_def("OLDUSDT", status="SETTLING"),
                     symbol_def("BTCUSDT_261225", "CURRENT_QUARTER"),
                     symbol_def("BTCUSDC", quote="USDC")],
            tickers=[{"symbol": "BTCUSDT", "quoteVolume": "3630949784.33", "lastPrice": "84867.90"},
                     {"symbol": "XAUUSDT", "quoteVolume": "5000000", "lastPrice": "2650.1"},
                     {"symbol": "OLDUSDT", "quoteVolume": "10", "lastPrice": "0.1"},
                     {"symbol": "ETHBTC", "quoteVolume": "1", "lastPrice": "0.03"}])

    def test_only_usdt_perpetuals_are_stored(self):
        self.seed_pool(self.client())
        rows = {r["symbol"]: r["category"] for r in
                self.conn.execute('SELECT "symbol", "category" FROM crypto_symbol')}
        self.assertEqual(rows, {"BTCUSDT": "perpetual", "XAUUSDT": "tradifi", "OLDUSDT": "perpetual"})

    def test_pool_excludes_settling(self):
        """下架结算中的合约仍在 ticker 里，但 K 线已停止更新，不能进币池。"""
        self.seed_pool(self.client())
        pool = [p["symbol"] for p in db.symbol_pool(self.conn)]
        self.assertEqual(pool, ["BTCUSDT", "XAUUSDT"])

    def test_array_fields_stored_as_json_and_raw_is_lossless(self):
        self.seed_pool(self.client())
        row = self.conn.execute('SELECT "filters", "orderTypes", "raw" FROM crypto_symbol '
                                'WHERE "symbol"=?', ("BTCUSDT",)).fetchone()
        self.assertEqual(json.loads(row["filters"])[0]["tickSize"], "0.10")
        self.assertEqual(json.loads(row["orderTypes"]), ["LIMIT", "MARKET"])
        self.assertEqual(json.loads(row["raw"])["someFutureField"], "接口以后新增的字段")

    def test_resync_drops_symbols_no_longer_listed(self):
        self.seed_pool(self.client())
        sync.sync_symbols(self.conn, FakeClient(symbols=[symbol_def("BTCUSDT")]))
        rows = [r[0] for r in self.conn.execute('SELECT "symbol" FROM crypto_symbol')]
        self.assertEqual(rows, ["BTCUSDT"])

    def test_ticker_is_a_snapshot_of_known_symbols(self):
        self.seed_pool(self.client())
        rows = {r[0] for r in self.conn.execute('SELECT "symbol" FROM crypto_ticker_24hr')}
        self.assertEqual(rows, {"BTCUSDT", "XAUUSDT", "OLDUSDT"})   # ETHBTC 不在币池
        sync.sync_ticker(self.conn, FakeClient(tickers=[{"symbol": "BTCUSDT", "quoteVolume": "1"}]))
        rows = {r[0] for r in self.conn.execute('SELECT "symbol" FROM crypto_ticker_24hr')}
        self.assertEqual(rows, {"BTCUSDT"})

    def test_min_quote_volume_filter(self):
        self.seed_pool(self.client())
        pool = [p["symbol"] for p in db.symbol_pool(self.conn, min_quote_volume=1e7)]
        self.assertEqual(pool, ["BTCUSDT"])


class TimeTest(unittest.TestCase):
    def test_last_bar_is_always_unfinished_so_it_is_cut(self):
        """03:06 请求时，03:00 那根还没走完，最后一根已完成的是 02:00。"""
        self.assertEqual(sync.last_closed_open(HOUR, AT), AT - 6 * 60_000 - HOUR)

    def test_beijing_dates(self):
        # 北京 2026-09-27 00:00 = UTC 2026-09-26 16:00
        start = sync.beijing_day_start_ms("2026-09-27")
        self.assertEqual(sync.format_beijing(start), "2026-09-27 00:00")
        self.assertEqual(sync.beijing_day_end_ms("2026-09-27") - start, 86_400_000 - 1)


class PlanTest(CryptoTestCase):
    def setUp(self):
        super().setUp()
        self.seed_pool(FakeClient(symbols=[symbol_def("BTCUSDT"), symbol_def("ETHUSDT")]))
        self.pool = db.symbol_pool(self.conn)
        self.end_open = sync.last_closed_open(HOUR, AT)

    def seed_bars(self, symbol, opens):
        db.upsert(self.conn, db.kline_table("1h", "perpetual"), db.KLINE_COLUMNS,
                  [(symbol,) + tuple(bar(t)) for t in opens])
        self.conn.commit()

    def test_no_local_data_starts_at_retention_floor(self):
        tasks = sync.plan_kline_tasks(self.conn, "1h", self.pool, at_ms=AT)
        floor = self.end_open - sync.RETENTION_DAYS * sync.DAY_MS + HOUR
        self.assertEqual(tasks, [("perpetual", "BTCUSDT", floor, self.end_open),
                                 ("perpetual", "ETHUSDT", floor, self.end_open)])
        self.assertEqual((self.end_open - floor) // HOUR + 1, 1440)   # 60 天正好一次请求拉完

    def test_incremental_resumes_after_last_bar_and_skips_up_to_date(self):
        self.seed_bars("BTCUSDT", [self.end_open - 2 * HOUR])
        self.seed_bars("ETHUSDT", [self.end_open])                  # 已是最新
        tasks = sync.plan_kline_tasks(self.conn, "1h", self.pool, at_ms=AT)
        self.assertEqual(tasks, [("perpetual", "BTCUSDT", self.end_open - HOUR, self.end_open)])

    def test_explicit_range_refetches_everything_and_clamps_end(self):
        self.seed_bars("ETHUSDT", [self.end_open])
        tasks = sync.plan_kline_tasks(self.conn, "1h", self.pool, start="2026-09-01",
                                      end="2026-09-10", at_ms=AT)
        begin = sync.beijing_day_start_ms("2026-09-01")
        end_open = (sync.beijing_day_end_ms("2026-09-10") // HOUR) * HOUR
        self.assertEqual({t[1] for t in tasks}, {"BTCUSDT", "ETHUSDT"})
        self.assertTrue(all(t[2] == begin and t[3] == end_open for t in tasks))


class FetchTest(unittest.TestCase):
    def test_pages_long_ranges_and_sizes_limit_to_what_is_needed(self):
        client = FakeClient()
        end_open = sync.last_closed_open(HOUR, AT)
        begin = end_open - 2999 * HOUR                              # 3000 根
        rows, requests = sync.fetch_symbol_klines(client, "BTCUSDT", "1h", begin, end_open, at_ms=AT)
        self.assertEqual((len(rows), requests), (3000, 2))
        self.assertEqual([call[3] for call in client.kline_calls], [1500, 1500])
        # 增量只要几根时 limit 很小，权重按最低一档算
        client = FakeClient()
        sync.fetch_symbol_klines(client, "BTCUSDT", "1h", end_open - 2 * HOUR, end_open, at_ms=AT)
        self.assertEqual(client.kline_calls[0][3], 3)
        self.assertEqual(binance.kline_weight(3), 1)

    def test_end_time_excludes_unfinished_bar(self):
        client = FakeClient()
        end_open = sync.last_closed_open(HOUR, AT)
        sync.fetch_symbol_klines(client, "BTCUSDT", "1h", end_open - HOUR, end_open, at_ms=AT)
        self.assertEqual(client.kline_calls[0][2], end_open + HOUR - 1)
        self.assertLess(client.kline_calls[0][2], AT)

    def test_rows_keep_interface_types(self):
        rows, _ = sync.fetch_symbol_klines(FakeClient(), "BTCUSDT", "1h",
                                           sync.last_closed_open(HOUR, AT),
                                           sync.last_closed_open(HOUR, AT), at_ms=AT)
        self.assertEqual(len(rows[0]), 13)
        self.assertIsInstance(rows[0][1], int)       # open_time
        self.assertIsInstance(rows[0][2], str)       # open 是字符串，原样存

    def test_new_listing_returns_only_existing_bars(self):
        end_open = sync.last_closed_open(HOUR, AT)
        client = FakeClient(listed_from={"NEWUSDT": end_open - 509 * HOUR})
        rows, requests = sync.fetch_symbol_klines(client, "NEWUSDT", "1h",
                                                  end_open - 1439 * HOUR, end_open, at_ms=AT)
        self.assertEqual((len(rows), requests), (510, 1))


class SyncKlinesTest(CryptoTestCase):
    def client(self, **kwargs):
        return FakeClient(symbols=[symbol_def("BTCUSDT"), symbol_def("XAUUSDT", "TRADIFI_PERPETUAL")],
                          tickers=[{"symbol": "BTCUSDT", "quoteVolume": "1"},
                                   {"symbol": "XAUUSDT", "quoteVolume": "1"}], **kwargs)

    def test_rows_land_in_their_category_table_and_second_run_sends_nothing(self):
        client = self.client()
        self.seed_pool(client)
        with patch("api.crypto.sync.now_ms", return_value=AT):
            first = sync.sync_klines(self.conn, client, workers=2)
            self.assertEqual((first["rows"], first["up_to_date"]), (2880, 0))
            count = lambda cat: self.conn.execute(
                f"SELECT COUNT(*) FROM {db.kline_table('1h', cat)}").fetchone()[0]
            self.assertEqual((count("perpetual"), count("tradifi")), (1440, 1440))
            calls = len(client.kline_calls)
            second = sync.sync_klines(self.conn, client, workers=2)
        self.assertEqual((second["requests"], second["up_to_date"]), (0, 2))
        self.assertEqual(len(client.kline_calls), calls)

    def test_restricted_region_aborts_the_whole_run(self):
        client = self.client(fail={"BTCUSDT": binance.BinanceRestricted(binance.RESTRICTED_MESSAGE),
                                   "XAUUSDT": binance.BinanceRestricted(binance.RESTRICTED_MESSAGE)})
        self.seed_pool(client)
        with self.assertRaisesRegex(binance.BinanceRestricted, "切到"):
            sync.sync_klines(self.conn, client, workers=1)

    def test_single_symbol_failure_does_not_stop_others(self):
        client = self.client(fail={"XAUUSDT": binance.BinanceError("Invalid symbol.")})
        self.seed_pool(client)
        with patch("api.crypto.sync.now_ms", return_value=AT):
            stats = sync.sync_klines(self.conn, client, workers=1)
        self.assertEqual((stats["failed"], stats["rows"]), (1, 1440))


class ClientTest(unittest.TestCase):
    """HTTP 层：451 / 418 / 429 的区分处理和按权重自适应限速。"""

    def http_error(self, code, headers=None):
        message = Message()
        for key, value in (headers or {}).items():
            message[key] = value
        return urllib.error.HTTPError("https://fapi.binance.com/x", code, "err", message,
                                      io.BytesIO(b'{"code": -1, "msg": "boom"}'))

    def make_client(self):
        self.sleeps = []
        self.now = [1000.0]
        client = binance.BinanceClient(sleep=lambda s: (self.sleeps.append(s),
                                                        self.now.__setitem__(0, self.now[0] + s)),
                                       clock=lambda: self.now[0])
        return client

    def test_451_is_reported_as_restricted_region(self):
        client = self.make_client()
        with patch.object(client._opener, "open", side_effect=self.http_error(451)):
            with self.assertRaisesRegex(binance.BinanceRestricted, "受限地区"):
                client.ping()

    def test_418_aborts(self):
        client = self.make_client()
        with patch.object(client._opener, "open", side_effect=self.http_error(418)):
            with self.assertRaises(binance.BinanceBanned):
                client.ping()

    def test_429_backs_off_before_retrying(self):
        client = self.make_client()

        class OK:
            headers = {"x-mbx-used-weight-1m": "10"}
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, *args): return b"{}"

        responses = [self.http_error(429, {"Retry-After": "7"}), OK()]

        def fake_open(request, timeout=None):
            result = responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        with patch.object(client._opener, "open", side_effect=fake_open), \
             patch("api.crypto.binance.json.load", return_value={}):
            client.ping()
        self.assertEqual(self.sleeps, [7])     # 先退避 7 秒，再重试，不是立即重试
        self.assertEqual(client.requests, 2)

    def test_soft_limit_waits_for_next_minute(self):
        client = self.make_client()
        client._record_weight({"x-mbx-used-weight-1m": "1900"})
        client._wait_turn()
        self.assertEqual(len(self.sleeps), 1)
        self.assertGreater(self.sleeps[0], 0)
        self.assertEqual(client.used_weight, 1900)

    def test_error_body_message_is_kept(self):
        client = self.make_client()
        with patch.object(client._opener, "open", side_effect=self.http_error(400)):
            with self.assertRaisesRegex(binance.BinanceError, "boom"):
                client.ping()


class ReaderAndMaintenanceTest(CryptoTestCase):
    def setUp(self):
        super().setUp()
        self.seed_pool(FakeClient(symbols=[symbol_def("BTCUSDT"), symbol_def("ETHUSDT")]))
        # UTC 2026-09-27 00:00 那根
        self.t0 = sync.beijing_day_start_ms("2026-09-27") + 8 * HOUR
        db.upsert(self.conn, db.kline_table("1h", "perpetual"), db.KLINE_COLUMNS,
                  [("BTCUSDT",) + tuple(bar(self.t0 + i * HOUR, 100 + i)) for i in range(3)])
        self.conn.commit()

    def test_reader_converts_types_and_uses_beijing_time(self):
        frame = load_kline(self.conn, symbols=["BTCUSDT"])
        self.assertEqual(frame["date"].tolist()[0], "2026-09-27 08:00:00")
        self.assertEqual(frame["close"].tolist(), [100.0, 101.0, 102.0])
        self.assertEqual(frame["open_time"].tolist()[0], self.t0)

    def test_reader_can_select_columns(self):
        frame = load_kline(self.conn, symbols=["BTCUSDT"], columns=["close"])
        self.assertEqual(list(frame.columns), ["category", "date", "symbol", "open_time", "close"])

    def test_inventory_counts_bars_and_filters(self):
        rows = {r["symbol"]: r for r in db.symbol_inventory(self.conn, ["perpetual"])}
        self.assertEqual((rows["BTCUSDT"]["bars"], rows["ETHUSDT"]["bars"]), (3, 0))
        self.assertEqual([r["symbol"] for r in db.symbol_inventory(
            self.conn, ["perpetual"], having="without")], ["ETHUSDT"])
        self.assertEqual([r["symbol"] for r in db.symbol_inventory(
            self.conn, ["perpetual"], having="with")], ["BTCUSDT"])

    def test_cleanup_preview_then_apply(self):
        with patch("api.crypto.sync.now_ms", return_value=self.t0 + 60 * sync.DAY_MS + HOUR + 1):
            preview = sync.cleanup(self.conn, keep_days=60, dry_run=True)
            self.assertEqual(preview["total"], 2)
            applied = sync.cleanup(self.conn, keep_days=60, dry_run=False)
        self.assertEqual(applied["total"], 2)
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM crypto_kline_1h_perpetual").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
