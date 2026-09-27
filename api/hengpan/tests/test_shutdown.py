"""
停止扫描与数据源异常的回归测试：这些场景曾导致扫描无法停止、后端进程空转数小时。

在项目根目录运行：api/.venv/bin/python -m unittest api.hengpan.tests.test_shutdown -v
"""
import socket
import threading
import time
import unittest
from unittest.mock import patch

import pandas as pd

from api import baostock_patch, data_fetcher
from api.baostock_patch import BaostockConnectionLost
from api.data_fetcher import BaostockBlacklisted, baostock_logout, is_blacklist_error
from api.hengpan import fetcher
from api.hengpan.router import HengpanRule
from api.hengpan.scanner import new_stats, scan_anchored_box


class FakeSocket:
    """连接已被对端关闭的 socket：recv 立刻返回空字节，正是触发死循环的条件。"""

    def __init__(self):
        self.timeout = None

    def settimeout(self, value):
        self.timeout = value

    def send(self, _payload):
        return None

    def recv(self, _size):
        return b""


class SendMsgPatchTest(unittest.TestCase):
    """补丁前 send_msg 会在 recv 返回空字节时无限空转，补丁后必须抛异常。"""

    def test_dead_connection_raises_instead_of_spinning(self):
        import baostock.common.context as context
        with patch.object(context, "default_socket", FakeSocket(), create=True):
            done = threading.Event()
            error = []

            def call():
                try:
                    baostock_patch._send_msg("ping")
                except BaostockConnectionLost as e:
                    error.append(e)
                finally:
                    done.set()

            threading.Thread(target=call, daemon=True).start()
            self.assertTrue(done.wait(3), "send_msg 在连接断开时没有及时返回，仍在空转")
            self.assertEqual(len(error), 1)

    def test_patch_is_idempotent(self):
        import baostock.util.socketutil as socketutil
        baostock_patch.apply_patch()
        first = socketutil.send_msg
        baostock_patch.apply_patch()
        self.assertIs(socketutil.send_msg, first)

    def test_patch_is_installed_on_import(self):
        import baostock.util.socketutil as socketutil
        self.assertTrue(getattr(socketutil.send_msg, "_hengpan_patched", False))


class LogoutTimeoutTest(unittest.TestCase):
    """登出卡死时必须超时放弃，否则调用方永远回不来（扫描停在「正在停止扫描…」）。"""

    def setUp(self):
        data_fetcher._thread_local.logged_in = True
        self.addCleanup(setattr, data_fetcher._thread_local, "logged_in", False)

    def test_hanging_logout_gives_up_and_returns(self):
        started = threading.Event()

        def hang():
            started.set()
            time.sleep(30)

        with patch.object(data_fetcher, "LOGOUT_TIMEOUT", 0.3), \
                patch.object(data_fetcher.bs, "logout", side_effect=hang):
            began = time.monotonic()
            baostock_logout()
            elapsed = time.monotonic() - began

        self.assertTrue(started.is_set())
        self.assertLess(elapsed, 5, "登出没有在超时后放弃，调用方被卡住了")
        # 超时后连接不能再被复用，否则下次查询会继续用这个坏连接
        self.assertFalse(data_fetcher._thread_local.logged_in)

    def test_normal_logout_still_clears_flag(self):
        with patch.object(data_fetcher.bs, "logout") as logout:
            baostock_logout()
        logout.assert_called_once()
        self.assertFalse(data_fetcher._thread_local.logged_in)

    def test_logout_without_login_is_a_noop(self):
        data_fetcher._thread_local.logged_in = False
        with patch.object(data_fetcher.bs, "logout") as logout:
            baostock_logout()
        logout.assert_not_called()


class BlacklistTest(unittest.TestCase):
    """黑名单是整轮性的：继续重试只会加重封禁，必须立刻中止整轮扫描。"""

    def test_recognises_blacklist_messages(self):
        self.assertTrue(is_blacklist_error("黑名单用户，请与管理员联系"))
        self.assertTrue(is_blacklist_error("10001011"))
        self.assertFalse(is_blacklist_error("网络超时"))

    def test_query_does_not_retry_on_blacklist(self):
        with patch.object(fetcher, "baostock_login",
                          side_effect=BaostockBlacklisted("黑名单用户")), \
                patch.object(fetcher, "baostock_relogin") as relogin:
            with self.assertRaises(BaostockBlacklisted):
                fetcher.query_kline("sh.600000", "date", "2026-01-01", "2026-01-10",
                                    retry_attempts=3)
        relogin.assert_not_called()

    def test_blacklist_in_response_body_also_aborts(self):
        class Result:
            error_code = "10001011"
            error_msg = "黑名单用户，请与管理员联系"

            def next(self):
                return False

        with patch.object(fetcher, "baostock_login"), \
                patch.object(fetcher.bs, "query_history_k_data_plus", return_value=Result()), \
                patch.object(fetcher, "baostock_relogin") as relogin:
            with self.assertRaises(BaostockBlacklisted):
                fetcher.query_kline("sh.600000", "date", "2026-01-01", "2026-01-10",
                                    retry_attempts=3)
        relogin.assert_not_called()

    def test_ordinary_error_still_retries(self):
        with patch.object(fetcher, "baostock_login"), \
                patch.object(fetcher.bs, "query_history_k_data_plus",
                             side_effect=socket.timeout("timed out")), \
                patch.object(fetcher, "baostock_relogin") as relogin, \
                patch.object(fetcher.time, "sleep"):
            with self.assertRaises(ConnectionError) as ctx:
                fetcher.query_kline("sh.600000", "date", "2026-01-01", "2026-01-10",
                                    retry_attempts=3)
        self.assertNotIsInstance(ctx.exception, BaostockBlacklisted)
        self.assertEqual(relogin.call_count, 2)


def _stock(code):
    return {"code": code, "name": code, "industry": "测试"}


class ScanAbortTest(unittest.TestCase):
    """扫描层面：黑名单中止、取消及时生效。"""

    PARAMS = {"max_workers": 2, "retry_attempts": 1}

    def setUp(self):
        self.rules = [{"id": "1", "params": HengpanRule().model_dump()}]
        self.stocks = [_stock(f"sh.60000{i}") for i in range(20)]

    def _run(self, fetch_side_effect, should_cancel=None):
        stats = new_stats("2026-09-24", self.rules)
        with patch("api.hengpan.scanner.ProcessPoolExecutor", ThreadPoolAsProcessPool), \
                patch("api.hengpan.scanner.fetch_kline", side_effect=fetch_side_effect):
            found = scan_anchored_box(self.stocks, self.rules, self.PARAMS, "2026-09-24", stats,
                                      should_cancel=should_cancel, frequency="d")
        return found, stats

    def test_blacklist_aborts_the_whole_scan(self):
        def blacklisted(*_args, **_kwargs):
            raise BaostockBlacklisted("黑名单用户，请与管理员联系")

        with self.assertRaises(ConnectionError) as ctx:
            self._run(blacklisted)
        self.assertIn("黑名单", str(ctx.exception))

    def test_cancel_stops_quickly(self):
        calls = []

        def slow(*_args, **_kwargs):
            calls.append(1)
            time.sleep(0.05)
            return pd.DataFrame()

        # 第一批结果处理完就请求取消
        state = {"cancel": False}

        def should_cancel():
            if len(calls) >= 2:
                state["cancel"] = True
            return state["cancel"]

        began = time.monotonic()
        found, _ = self._run(slow, should_cancel=should_cancel)
        elapsed = time.monotonic() - began

        self.assertLess(elapsed, 10, "取消后扫描没有及时收口")
        self.assertLess(len(calls), len(self.stocks), "取消后仍然扫完了全部股票")
        self.assertEqual(found, [])


class ThreadPoolAsProcessPool:
    """用线程池替身跑扫描：免去 spawn 子进程，测试里能直接 patch fetch_kline。"""

    def __init__(self, max_workers=None, initializer=None, **_kwargs):
        from concurrent.futures import ThreadPoolExecutor
        self._pool = ThreadPoolExecutor(max_workers=max_workers)
        if initializer:
            pass  # 线程替身不做 baostock 登录

    def submit(self, fn, *args, **kwargs):
        return self._pool.submit(fn, *args, **kwargs)

    def shutdown(self, wait=True, cancel_futures=False):
        self._pool.shutdown(wait=wait, cancel_futures=cancel_futures)


if __name__ == "__main__":
    unittest.main()
