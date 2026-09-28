"""
Binance USDT 本位永续合约的行情接口客户端。只用公开接口，不需要 API Key。

研究文档里踩过的坑都在这里处理：
- 不读环境变量里的代理（相当于 requests 的 trust_env=False）。本机 Clash TUN 已经接管路由，
  再叠一层 HTTPS_PROXY 会形成双重代理，并发一高就大量超时。
- 限速按 IP 每分钟 2400 权重。每个响应头 x-mbx-used-weight-1m 是本分钟已用权重，
  超过 1800 主动等到下一分钟；429 按 Retry-After 退避后再试，绝不立即重试；
  418 说明已被临时封 IP，整轮中止。
- 451 是出口 IP 在 Binance 受限地区，单独提示切换代理节点，不笼统报「网络错误」。
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://fapi.binance.com"
WEIGHT_LIMIT = 2400          # exchangeInfo 的 rateLimits 给的每分钟上限
WEIGHT_SOFT_LIMIT = 1800     # 超过 75% 就主动等下一分钟
KLINE_MAX_LIMIT = 1500       # 单次最多 1500 根，填 1501 报错 -1130
USER_AGENT = "Mozilla/5.0 (hengpan-local-store)"


class BinanceError(Exception):
    """Binance 接口返回的普通错误。"""


class BinanceRestricted(BinanceError):
    """HTTP 451：出口 IP 在受限地区。换节点之前重试没有意义，整轮中止。"""


class BinanceBanned(BinanceError):
    """HTTP 418：无视 429 继续请求被临时封 IP，整轮中止。"""


class BinanceRateLimited(BinanceError):
    """HTTP 429：本分钟权重用完，调用方应在等待后再试。"""


RESTRICTED_MESSAGE = ("当前网络出口在 Binance 受限地区（HTTP 451），"
                      "请把代理切到新加坡、日本等节点后重试")
BANNED_MESSAGE = "Binance 已临时封禁当前 IP（HTTP 418），本轮中止，请过一段时间再试"


def kline_weight(limit):
    """K 线接口按 limit 分档的权重（官方文档口径）。"""
    if limit <= 100:
        return 1
    if limit <= 500:
        return 2
    if limit <= 1000:
        return 5
    return 10


class BinanceClient:
    """线程安全：多个工作线程共用一个实例，权重计数和等待状态加锁维护。"""

    def __init__(self, base_url=BASE_URL, sleep=time.sleep, clock=time.time):
        self.base_url = base_url
        # 空的 ProxyHandler = 不读 HTTP(S)_PROXY 环境变量，交给系统路由（Clash TUN）
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self._lock = threading.Lock()
        self._sleep = sleep
        self._clock = clock
        self._pause_until = 0.0
        self.used_weight = 0
        self.requests = 0

    # ---- 限速 ----

    def _wait_turn(self):
        """如果处于退避期，等到退避结束再发请求。"""
        with self._lock:
            delay = self._pause_until - self._clock()
        if delay > 0:
            self._sleep(delay)

    def _pause(self, seconds):
        with self._lock:
            self._pause_until = max(self._pause_until, self._clock() + seconds)

    def _record_weight(self, headers):
        value = headers.get("x-mbx-used-weight-1m") if headers else None
        if value is None:
            return
        try:
            used = int(value)
        except ValueError:
            return
        with self._lock:
            self.used_weight = used
        if used >= WEIGHT_SOFT_LIMIT:
            # 权重按自然分钟重置，等到下一分钟开头再多留 1 秒
            now = self._clock()
            self._pause(60 - (now % 60) + 1)

    # ---- 请求 ----

    def get(self, path, params=None, timeout=30, retries=1):
        """
        GET 一个公开接口，返回解析后的 JSON。

        429 会按 Retry-After 退避后重试 retries 次；451 / 418 直接抛出让整轮中止。
        """
        query = urllib.parse.urlencode(params or {})
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        attempt = 0
        while True:
            self._wait_turn()
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with self._lock:
                self.requests += 1
            try:
                with self._opener.open(request, timeout=timeout) as response:
                    self._record_weight(response.headers)
                    return json.load(response)
            except urllib.error.HTTPError as error:
                self._record_weight(error.headers)
                if error.code == 451:
                    raise BinanceRestricted(RESTRICTED_MESSAGE) from error
                if error.code == 418:
                    raise BinanceBanned(BANNED_MESSAGE) from error
                if error.code == 429:
                    retry_after = _retry_after(error.headers)
                    self._pause(retry_after)
                    if attempt < retries:
                        attempt += 1
                        continue
                    raise BinanceRateLimited(
                        f"Binance 限速（HTTP 429），已退避 {retry_after} 秒仍未恢复") from error
                raise BinanceError(_error_message(error)) from error
            except urllib.error.URLError as error:
                raise BinanceError(f"连不上 Binance：{error.reason}") from error
            except TimeoutError as error:
                raise BinanceError(f"请求 Binance 超时（{timeout} 秒）") from error

    # ---- 具体接口 ----

    def exchange_info(self):
        """合约元信息，权重 1。响应较大，实测容易超时，超时设到 60 秒。"""
        return self.get("/fapi/v1/exchangeInfo", timeout=60)

    def ticker_24hr(self):
        """全市场 24 小时行情，一次返回全部交易对，权重 40。"""
        return self.get("/fapi/v1/ticker/24hr", timeout=60)

    def klines(self, symbol, interval, start_time=None, end_time=None, limit=KLINE_MAX_LIMIT):
        """K 线，返回 12 个元素的数组列表。end_time 用来截掉未走完的末根。"""
        params = {"symbol": symbol, "interval": interval, "limit": min(limit, KLINE_MAX_LIMIT)}
        if start_time is not None:
            params["startTime"] = int(start_time)
        if end_time is not None:
            params["endTime"] = int(end_time)
        return self.get("/fapi/v1/klines", params, timeout=40)

    def ping(self):
        """连通性检测，权重 1。能区分 451（地区受限）和一般网络故障。"""
        return self.get("/fapi/v1/ping", timeout=15)


def _retry_after(headers):
    try:
        return max(1, int(headers.get("Retry-After", "60")))
    except (TypeError, ValueError):
        return 60


def _error_message(error):
    """把 Binance 的 {"code": -1121, "msg": "Invalid symbol."} 拼进错误信息。"""
    try:
        body = json.loads(error.read().decode("utf-8") or "{}")
        return f"Binance 返回 HTTP {error.code}：{body.get('msg') or body}"
    except Exception:
        return f"Binance 返回 HTTP {error.code}"
