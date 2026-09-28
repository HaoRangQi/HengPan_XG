"""
横盘选股扫描：多进程逐只拉取所选周期 K 线，对每只股票按多组规则各算一遍，边扫边把命中的股票交给调用方。
进程池、停止和进度回调的写法照搬 api/platform_scanner.py 的 scan_stocks。
"""
import socket
from bisect import bisect_left, bisect_right
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from datetime import datetime, timedelta

from colorama import Fore, Style

from .. import baostock_patch
from ..data_fetcher import BaostockBlacklisted, baostock_login
from ..process_pool import close_process_pool
from .anchored_box import BOUNDARY_BAND, BOX_TYPE, check_series, extract_series
from .fetcher import fetch_kline
from ..store.reader import load_one_kline_60m

# 卡片和大图用到的 K 线字段
KLINE_COLUMNS = ["date", "open", "high", "low", "close", "volume", "amount", "turn"]
# 一只都没取到、却已连续失败这么多只时，认为数据源整体不可用，提前结束
ABORT_AFTER_FAILURES = 50
# 返回结果的上限。每只股票带着上百根 K 线，规则放得很松时命中上千只会把响应撑到几十 MB，
# 超出部分只计数不返回，并在 stats.truncated 里如实告知。
MAX_RESULTS = 400
# 子进程的 socket 超时（秒）。baostock 建连接时不设超时，服务端不响应时 recv 会一直等下去
SOCKET_TIMEOUT = 30


def _init_worker():
    """扫描子进程初始化：先设 socket 超时，卡住的请求会抛异常并走重试；再登录 baostock。"""
    socket.setdefaulttimeout(SOCKET_TIMEOUT)
    # 子进程是 spawn 出来的，要在这里重新打上 baostock 收包补丁
    baostock_patch.apply_patch()
    baostock_login()


def fetch_local_kline(db_path, code, start_date, end_date):
    """子进程只读本地 SQLite，不建立 Baostock 连接。"""
    return load_one_kline_60m(db_path, code, start_date, end_date, adjust="qfq")


def select_stocks(stock_basics_df, industry_df):
    """
    股票池：只保留上市中的股票（type=1、status=1）。
    首页的 prepare_stock_list 只排除指数，ETF、可转债会混进来；货币 ETF 价格几乎不动，会被当成十字星选中。
    """
    basics = stock_basics_df[(stock_basics_df["type"] == "1") & (stock_basics_df["status"] == "1")]
    industries = dict(zip(industry_df["code"], industry_df["industry"])) if not industry_df.empty else {}
    return [{"code": row.code, "name": row.code_name, "industry": industries.get(row.code) or "未知行业"}
            for row in basics.itertuples(index=False)]


def new_stats(scan_date, rules):
    """
    扫描统计。跳过原因是全局的（一只股票对所有规则一起跳过），入选和分界情况按规则分别统计。
    这些计数不受 MAX_RESULTS 截断影响，始终是真实值。
    """
    return {
        "scan_date": scan_date,
        # stale 扫描日没有交易（停牌、未上市或数据未更新）/ insufficient 有效 K 线不足 / failed 取数失败
        # suspended 每组规则的回验窗口里都有停牌缺失的交易日
        "skipped": {"stale": 0, "insufficient": 0, "failed": 0, "suspended": 0},
        "truncated": 0,
        "rules": {rule["id"]: {
            "analyzed": 0,        # 有效 K 线够这组规则回验的只数
            "passed_full": 0,     # 整体口径入选
            "passed_body": 0,     # 实体口径入选
            "near": 0,            # 末端振幅在十字星分界附近（只统计固定箱高的规则组）
            "rescued": 0,         # 其中换一种模式锚定就能入选
            "suspended": 0,       # 回验窗口里有停牌缺失，这组规则不判定
            "over_amplitude": 0,  # 末端振幅超过振幅上限被淘汰（只有振幅模式会用到）
        } for rule in rules},
    }


def window_has_gap(dates, lookback, trading_days):
    """
    回验窗口（末端 + 之前 lookback 根）里是否缺了交易日。

    停牌那几天 Baostock 不返回分钟线，K 线会直接接上，停牌前后被压成一段看似连续的走势。
    这种窗口不能当横盘箱体看，也不能补 0 或补前收盘价（补前收会变成一条完美的水平线，正好被误判成箱体）。

    dates：该股票的 K 线时间序列（'YYYY-MM-DD' 或 'YYYY-MM-DD HH:MM:SS'），升序
    trading_days：交易日历（'YYYY-MM-DD'），升序；为空时无法判断，视为无缺口
    """
    if not trading_days or dates is None or len(dates) < lookback + 1:
        return False
    window = [str(value)[:10] for value in dates[len(dates) - lookback - 1:]]
    first, last = window[0], window[-1]
    present = set(window)
    lo = bisect_left(trading_days, first)
    hi = bisect_right(trading_days, last)
    return any(day not in present for day in trading_days[lo:hi])


def fetch_range(scan_date, max_lookback, frequency="60"):
    """取数起止日期，并为所选周期的回验根数预留节假日缓冲。"""
    if frequency not in ("d", "60"):
        raise ValueError("frequency must be 'd' or '60'")
    # A trading day has roughly four 60-minute bars.  The generous buffer also
    # covers holidays and newly listed/stale securities without falling back to
    # daily data.
    days = max(60, int((max_lookback + 1) * (2.5 if frequency == "d" else 0.7)))
    start = datetime.strptime(scan_date, "%Y-%m-%d") - timedelta(days=days)
    return start.strftime("%Y-%m-%d"), scan_date


def build_item(stock, df, matches, scan_date, frequency="60"):
    """把一只命中的股票整理成接口返回的结构。上轨下轨按规则各不相同，都放在 matches 里。"""
    kline = df[KLINE_COLUMNS]
    last = df.iloc[-1]
    return {
        "code": stock["code"],
        "name": stock["name"],
        "industry": stock["industry"],
        "is_st": df["isST"].iloc[-1] == "1",
        "date": str(last["date"]),
        "close": float(last["close"]),
        "amplitude": float((last["high"] - last["low"]) / last["close"]),
        "matches": matches,
        "kline_data": kline.astype(object).where(kline.notna(), None).to_dict(orient="records"),
    }


def analyze_stock(stock, df, rules, scan_date, stats, frequency="60", trading_days=None):
    """
    单只股票：跳过没有扫描日数据和数据不足的，其余按每组规则各算一遍。
    只要有一组规则实体口径通过就返回结果条目，命中的规则都记在 matches 里。

    trading_days：交易日历（升序）。给了就检查每组规则的回验窗口，窗口里有停牌缺失的交易日时
    这组规则不判定；没给（例如本地没有交易日历）时不做这项检查。
    """
    if frequency not in ("d", "60"):
        raise ValueError("frequency must be 'd' or '60'")
    latest_day = str(df["date"].iloc[-1])[:10] if not df.empty else None
    if df.empty or latest_day != scan_date:
        stats["skipped"]["stale"] += 1
        return None

    series = extract_series(df)
    matches = {}
    analyzed = suspended = False
    for rule in rules:
        if window_has_gap(series["date"], rule["params"]["lookback"], trading_days):
            stats["rules"][rule["id"]]["suspended"] += 1
            suspended = True
            continue
        box = check_series(series, **rule["params"])
        if box is None:  # 有效 K 线不够这组规则回验，换下一组
            continue
        analyzed = True
        counter = stats["rules"][rule["id"]]
        counter["analyzed"] += 1
        # 十字星分界只存在于固定箱高模式，振幅模式不区分十字星
        if rule["params"].get("box_type", BOX_TYPE) == "fixed" and \
                abs(box["amplitude"] - rule["params"]["doji_amplitude"]) <= BOUNDARY_BAND:
            counter["near"] += 1
            other = "normal" if box["mode"] == "doji" else "doji"
            if not box["passed_full"] and check_series(series, **rule["params"], mode=other)["passed_full"]:
                counter["rescued"] += 1
        counter["over_amplitude"] += bool(box.get("over_amplitude"))
        counter["passed_full"] += box["passed_full"]
        counter["passed_body"] += box["passed_body"]
        if box["passed_body"]:
            matches[rule["id"]] = box

    if not analyzed:
        # 没有一组规则能判定：只要有一组是因为停牌缺口，就记停牌，否则记数据不足
        stats["skipped"]["suspended" if suspended else "insufficient"] += 1
        return None
    return build_item(stock, df, matches, scan_date, frequency=frequency) if matches else None


def scan_anchored_box(stock_list, rules, params, scan_date, stats,
                      update_progress=None, should_cancel=None, on_found=None,
                      frequency="60", local_db_path=None, trading_days=None):
    """
    逐只扫描股票池，返回至少命中一组规则的股票（按代码排序）。

    rules：[{"id", "params": {box_type, doji_amplitude, box_height, amp_multiple, lookback, max_breach}}]，一次取数全部算完
    params：max_workers / retry_attempts
    stats：new_stats() 生成的统计，扫描过程中原地更新，调用方可以随时读取
    update_progress(scanned, total, found, message)：进度回调
    should_cancel()：返回 True 时停止，已找到的结果照常返回
    on_found(item)：每命中一只就回调一次，用于边扫边出

    返回的是实体口径命中的股票，它包含整体口径的全部入选股，前端按口径和规则切换显示。
    """
    if frequency not in ("d", "60"):
        raise ValueError("frequency must be 'd' or '60'")
    max_lookback = max(rule["params"]["lookback"] for rule in rules)
    start_date, end_date = fetch_range(scan_date, max_lookback, frequency=frequency)
    total = len(stock_list)

    print(f"{Fore.CYAN}======================================{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Starting anchored box scan{Style.RESET_ALL}")
    print(f"  - Scan date: {Fore.GREEN}{scan_date}{Style.RESET_ALL} (data from {start_date}, frequency {frequency})")
    for rule in rules:
        print(f"  - Rule {rule['id']}: {Fore.GREEN}{rule['params']}{Style.RESET_ALL}")
    print(f"  - Stocks: {Fore.GREEN}{total}{Style.RESET_ALL}, workers: {params['max_workers']}")
    print(f"{Fore.CYAN}======================================{Style.RESET_ALL}")

    found = []
    scanned = fetched = 0
    cancelled = False
    use_local = frequency == "60" and local_db_path
    executor = ProcessPoolExecutor(
        max_workers=params["max_workers"],
        initializer=None if use_local else _init_worker,
    )
    pending = {}
    next_index = 0
    window_size = max(1, params["max_workers"] * 2)

    def submit_window():
        """Keep only a small number of requests queued so cancellation takes effect."""
        nonlocal next_index
        while next_index < total and len(pending) < window_size:
            if should_cancel and should_cancel():
                return False
            stock = stock_list[next_index]
            if use_local:
                future = executor.submit(fetch_local_kline, local_db_path, stock["code"],
                                         start_date, end_date)
            else:
                future = executor.submit(fetch_kline, stock["code"], start_date, end_date,
                                         frequency, params["retry_attempts"])
            pending[future] = stock
            next_index += 1
        return True

    def process_future(future, stock):
        nonlocal scanned, fetched
        scanned += 1
        try:
            df = future.result()
            fetched += 1
        except BaostockBlacklisted as e:
            # 黑名单是整轮性的：继续扫只会不断撞墙并加重封禁，立刻中止
            stats["skipped"]["failed"] += 1
            raise ConnectionError(f"Baostock 已将本机列入黑名单，扫描中止。请等待解封后再试。原始错误：{e}")
        except Exception as e:
            stats["skipped"]["failed"] += 1
            print(f"{Fore.RED}Error fetching {stock['code']}: {e}{Style.RESET_ALL}")
            # 连续大量失败通常意味着数据源不可用，尽早退出而不是空转
            if fetched == 0 and stats["skipped"]["failed"] >= ABORT_AFTER_FAILURES:
                raise ConnectionError(f"连续 {ABORT_AFTER_FAILURES} 只股票取数失败，数据源可能不可用。最近一次错误：{e}")
            df = None

        if df is not None:
            item = analyze_stock(stock, df, rules, scan_date, stats, frequency=frequency,
                                 trading_days=trading_days)
            if item and len(found) < MAX_RESULTS:
                found.append(item)
                if on_found and not (should_cancel and should_cancel()):
                    on_found(item)
            elif item:
                stats["truncated"] += 1

        if update_progress and (scanned % 10 == 0 or scanned == total):
            update_progress(scanned=scanned, total=total, found=len(found),
                            message=f"已分析 {scanned}/{total} 只，找到 {len(found)} 只横盘股")

    aborted = False
    try:
        if not submit_window():
            cancelled = True
        while pending:
            done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
            for future in done:
                stock = pending.pop(future)
                # Do not publish new results after cancellation has been requested.
                if should_cancel and should_cancel():
                    cancelled = True
                    break
                process_future(future, stock)
            if cancelled:
                print(f"{Fore.YELLOW}Cancel requested, stopping scan ({scanned}/{total} processed){Style.RESET_ALL}")
                break
            if not submit_window():
                cancelled = True
                print(f"{Fore.YELLOW}Cancel requested, stopping scan ({scanned}/{total} processed){Style.RESET_ALL}")
                break
    except Exception:
        aborted = True
        raise
    finally:
        close_process_pool(executor, pending, force=aborted or cancelled or bool(pending))

    if fetched == 0 and stats["skipped"]["failed"] and not cancelled:
        source = "本地行情库" if use_local else "数据源"
        raise ConnectionError(f"全部 {stats['skipped']['failed']} 只股票取数失败，{source}可能不可用")

    found.sort(key=lambda item: item["code"])  # 前端会按当前规则重新排序，这里只求顺序稳定
    summary = "、".join(f"{rule['id']} 组 {stats['rules'][rule['id']]['passed_full']} 只" for rule in rules)
    print(f"{Fore.CYAN}Anchored box scan {'cancelled' if cancelled else 'completed'}: "
          f"{scanned}/{total} processed, returned {len(found)}, truncated {stats['truncated']}, "
          f"passed full by rule: {summary}{Style.RESET_ALL}")
    if update_progress:
        update_progress(scanned=scanned, total=total, found=len(found),
                        message=f"{'已停止' if cancelled else '扫描完成'}：分析 {scanned} 只，"
                                f"命中 {len(found) + stats['truncated']} 只，整体口径入选 {summary}")
    return found
