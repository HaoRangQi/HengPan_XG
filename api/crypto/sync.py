"""
加密货币同步任务：从 Binance 增量拉取数据写入 crypto.db。只有这个模块会联网。

每次同步的请求构成：
- exchangeInfo（权重 1）：币池定义，12 小时内同步过就跳过
- ticker/24hr（权重 40）：全市场行情快照，用于流动性过滤和列表展示
- klines：每个交易对 1 次（区间超过 1500 根时翻页）。已是最新的交易对不发请求

727 个交易对首次拉 60 天 1 小时线（1440 根，单次请求权重 10），总权重约 7300，
按每分钟 2400 的上限约 3~4 分钟；之后的增量每次只拉几根，权重 1。
"""
import json
import os
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone

from colorama import Fore, Style

from ..store.sync import finish_log, recent_logs, start_log
from . import db
from .binance import (KLINE_MAX_LIMIT, BinanceBanned, BinanceClient, BinanceError,
                      BinanceRestricted)

# 本地保留多少天的 1 小时线，60 天 = 1440 根，一次请求就能拉完
RETENTION_DAYS = 60
# 并发线程数。研究文档实测 8 和 16 吞吐一样，8 就够
SYNC_WORKERS = 8
# 缓冲区攒够这么多根 K 线就批量写一次库
WRITE_BATCH_ROWS = 20_000
# 一个都没成功、却已连续失败这么多个时，认为数据源整体不可用
ABORT_AFTER_FAILURES = 30
# 币池定义隔这么久才重新拉
METADATA_MAX_AGE = timedelta(hours=12)

DAY_MS = 86_400_000
BEIJING = timezone(timedelta(hours=8))


# --------------------------------------------------------------------------
# 时间换算：界面上的日期一律按北京时间理解，库里存的是 UTC 毫秒
# --------------------------------------------------------------------------

def now_ms():
    return int(time.time() * 1000)


def last_closed_open(period_ms, at_ms=None):
    """最后一根已走完的 K 线的开盘时间。7×24 交易，任何时刻最后一根都没走完，必须截掉。"""
    at_ms = now_ms() if at_ms is None else at_ms
    return (at_ms // period_ms) * period_ms - period_ms


def beijing_day_start_ms(day):
    """北京时间某天 00:00 对应的 UTC 毫秒。"""
    moment = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=BEIJING)
    return int(moment.timestamp() * 1000)


def beijing_day_end_ms(day):
    """北京时间某天 23:59:59.999 对应的 UTC 毫秒。"""
    return beijing_day_start_ms(day) + DAY_MS - 1


def format_beijing(ms):
    """UTC 毫秒转北京时间字符串，日志和提示用。"""
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, BEIJING).strftime("%Y-%m-%d %H:%M")


# --------------------------------------------------------------------------
# 元数据：币池 / 24 小时行情
# --------------------------------------------------------------------------

def _symbol_row(symbol, updated_at):
    values = []
    for field in db.SYMBOL_FIELDS:
        value = symbol.get(field)
        if field in db.SYMBOL_JSON_FIELDS and value is not None:
            value = json.dumps(value, ensure_ascii=False)
        values.append(value)
    category = db.CONTRACT_CATEGORY.get(symbol.get("contractType"))
    return tuple(values) + (json.dumps(symbol, ensure_ascii=False), category, updated_at)


def sync_symbols(conn, client):
    """
    币池定义。只存 USDT 计价的两类永续（加密 PERPETUAL、传统资产 TRADIFI_PERPETUAL），
    季度交割合约不要。status 原样保留，下架结算中的 SETTLING 在取币池时再排除。

    crypto_symbol 是 exchangeInfo 的当前快照：接口里已经没有的交易对从表里删掉，
    它们的历史 K 线保留在 K 线表里。
    """
    info = client.exchange_info()
    now = datetime.now().isoformat(timespec="seconds")
    wanted = [s for s in info.get("symbols", [])
              if s.get("contractType") in db.CONTRACT_CATEGORY and s.get("quoteAsset") == "USDT"]
    rows = [_symbol_row(s, now) for s in wanted]
    written = db.upsert(conn, "crypto_symbol", db.SYMBOL_COLUMNS, rows)
    current = [s["symbol"] for s in wanted]
    if current:
        conn.execute('DELETE FROM crypto_symbol WHERE "symbol" NOT IN (%s)'
                     % ",".join("?" * len(current)), current)
    db.set_meta(conn, "symbols_synced_at", now)
    conn.commit()
    counts = {c: sum(1 for s in wanted if db.CONTRACT_CATEGORY[s["contractType"]] == c
                     and s.get("status") == "TRADING") for c in db.CATEGORIES}
    print(f"{Fore.GREEN}币池：{written} 个 USDT 永续，其中正在交易 "
          + "，".join(f"{db.CATEGORY_LABELS[c]} {n}" for c, n in counts.items())
          + Style.RESET_ALL)
    return written


def sync_ticker(conn, client):
    """
    全市场 24 小时行情。只存币池里有的交易对；整表替换成最新快照，
    避免已经不在的交易对留着旧成交额。
    """
    tickers = client.ticker_24hr()
    known = {row[0] for row in conn.execute('SELECT "symbol" FROM crypto_symbol')}
    now = datetime.now().isoformat(timespec="seconds")
    rows = [tuple(t.get(field) for field in db.TICKER_FIELDS) + (now,)
            for t in tickers if t.get("symbol") in known]
    conn.execute("DELETE FROM crypto_ticker_24hr")
    written = db.upsert(conn, "crypto_ticker_24hr", db.TICKER_COLUMNS, rows)
    conn.commit()
    print(f"{Fore.GREEN}24 小时行情：{written} 个交易对{Style.RESET_ALL}")
    return written


def _metadata_is_stale(conn):
    synced = db.get_meta(conn, "symbols_synced_at")
    if not synced:
        return True
    return datetime.now() - datetime.fromisoformat(synced) > METADATA_MAX_AGE


# --------------------------------------------------------------------------
# K 线
# --------------------------------------------------------------------------

def plan_kline_tasks(conn, interval, pool, start=None, end=None, at_ms=None):
    """
    每个交易对要拉的区间 [起点, 终点]，都是开盘时间（UTC 毫秒）。返回里只有需要请求的交易对。

    终点：最后一根已走完的 K 线；指定了 end（北京日期）就取两者较早的。
    起点：指定了 start（补历史）→ 所有交易对都从这天拉；
          否则按本地进度增量：有数据从最后一根的下一根开始，没有数据从保留期开头开始。
    起点晚于终点 = 本地已是最新，不发请求。
    """
    period = db.INTERVALS[interval]
    end_open = last_closed_open(period, at_ms)
    if end:
        end_open = min(end_open, (beijing_day_end_ms(end) // period) * period)
    fixed_start = None
    if start:
        # 向上对齐到周期边界
        fixed_start = -(-beijing_day_start_ms(start) // period) * period
    floor = end_open - RETENTION_DAYS * DAY_MS + period

    known = {}
    for category in {item["category"] for item in pool}:
        known.update(db.latest_open_times(conn, interval, category))

    tasks = []
    for item in pool:
        if fixed_start is not None:
            begin = fixed_start
        else:
            last = known.get(item["symbol"])
            begin = last + period if last is not None else floor
        if begin <= end_open:
            tasks.append((item["category"], item["symbol"], begin, end_open))
    return tasks


def fetch_symbol_klines(client, symbol, interval, begin, end_open, at_ms=None):
    """
    拉一个交易对 [begin, end_open] 的全部 K 线，区间超过 1500 根时按 startTime 翻页。

    endTime 取终点那根的收盘时间，确保不会拿到未走完的末根；
    再按收盘时间兜一次底（close_time 必须早于当前时刻）。
    返回 (行列表, 请求次数)。行是 (symbol, 下标 0~11 原样的值)。
    """
    period = db.INTERVALS[interval]
    at_ms = now_ms() if at_ms is None else at_ms
    rows, requests, cursor = [], 0, begin
    while cursor <= end_open:
        needed = (end_open - cursor) // period + 1
        limit = min(KLINE_MAX_LIMIT, needed)
        batch = client.klines(symbol, interval, start_time=cursor,
                              end_time=end_open + period - 1, limit=limit)
        requests += 1
        if not batch:
            break
        for item in batch:
            values = list(item[:len(db.KLINE_FIELDS)])
            values += [None] * (len(db.KLINE_FIELDS) - len(values))
            open_time, close_time = values[0], values[6]
            if open_time is None or open_time > end_open:
                continue
            if close_time is not None and close_time >= at_ms:
                continue   # 未走完
            rows.append((symbol,) + tuple(values))
        if len(batch) < limit:
            break   # 上市时间不够长，接口只返回实际存在的根数
        cursor = batch[-1][0] + period
    return rows, requests


def sync_klines(conn, client, interval="1h", categories=None, start=None, end=None,
                symbols=None, min_quote_volume=0, update_progress=None, should_cancel=None,
                workers=SYNC_WORKERS):
    """
    多线程逐个交易对拉 K 线，主线程统一写库（SQLite 同一时刻只能有一个写入者）。

    返回 {"rows", "requests", "failed", "cancelled", "up_to_date", "symbols", "used_weight"}。
    中途取消或出错，已写入的数据都保留，下次同步从断点继续。
    """
    categories = list(categories or db.CATEGORIES)
    if start and end and start > end:
        raise ValueError(f"起始日期 {start} 不能晚于结束日期 {end}")
    pool = db.symbol_pool(conn, categories, min_quote_volume=min_quote_volume, symbols=symbols)
    if not pool:
        raise ValueError("本地币池为空或没有符合条件的交易对，请先同步币池")
    tasks = plan_kline_tasks(conn, interval, pool, start=start, end=end)
    stats = {"rows": 0, "requests": 0, "failed": 0, "cancelled": False,
             "up_to_date": len(pool) - len(tasks), "symbols": len(pool), "used_weight": 0}

    print(f"{Fore.CYAN}同步 {interval} K 线：{'/'.join(db.CATEGORY_LABELS[c] for c in categories)}，"
          f"币池 {len(pool)} 个，待同步 {len(tasks)} 个，{stats['up_to_date']} 个已是最新{Style.RESET_ALL}")
    if not tasks:
        message = f"全部 {len(pool)} 个交易对已是最新，没有发请求"
        if update_progress:
            update_progress(done=0, total=0, rows=0, message=message)
        return stats

    total = len(tasks)
    buffers = {category: [] for category in categories}
    done = succeeded = 0
    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="binance")
    pending = {}
    next_index = 0
    window = workers * 2

    def flush(category=None):
        for name in ([category] if category else list(buffers)):
            if buffers[name]:
                db.upsert(conn, db.kline_table(interval, name), db.KLINE_COLUMNS, buffers[name])
                buffers[name] = []
        conn.commit()

    def submit_window():
        nonlocal next_index
        while next_index < total and len(pending) < window:
            if should_cancel and should_cancel():
                return False
            category, symbol, begin, end_open = tasks[next_index]
            future = executor.submit(fetch_symbol_klines, client, symbol, interval, begin, end_open)
            pending[future] = (category, symbol)
            next_index += 1
        return True

    try:
        if not submit_window():
            stats["cancelled"] = True
        while pending and not stats["cancelled"]:
            ready, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
            for future in ready:
                category, symbol = pending.pop(future)
                done += 1
                try:
                    rows, requests = future.result()
                except (BinanceRestricted, BinanceBanned):
                    raise   # 整轮性的，继续只会撞墙
                except BinanceError as error:
                    stats["failed"] += 1
                    print(f"{Fore.RED}取数失败 {symbol}: {error}{Style.RESET_ALL}")
                    if succeeded == 0 and stats["failed"] >= ABORT_AFTER_FAILURES:
                        raise BinanceError(
                            f"连续 {ABORT_AFTER_FAILURES} 个交易对取数失败，数据源可能不可用。最近错误：{error}")
                    continue
                succeeded += 1
                stats["requests"] += requests
                if rows:
                    buffers[category] += rows
                    stats["rows"] += len(rows)
                if sum(len(b) for b in buffers.values()) >= WRITE_BATCH_ROWS:
                    flush()
                if update_progress and (done % 10 == 0 or done == total):
                    update_progress(done=done, total=total, rows=stats["rows"],
                                    message=f"已同步 {done}/{total} 个交易对，写入 {stats['rows']} 根 K 线，"
                                            f"本分钟权重 {client.used_weight}/2400")
            if should_cancel and should_cancel():
                stats["cancelled"] = True
                break
            if not submit_window():
                stats["cancelled"] = True
    finally:
        for future in pending:
            future.cancel()
        # 在途请求最多几十秒就会返回，不等它们；线程是 daemon 式的池线程，结果直接丢弃
        executor.shutdown(wait=False, cancel_futures=True)
        flush()

    stats["used_weight"] = client.used_weight
    print(f"{Fore.GREEN}同步完成：写入 {stats['rows']} 根，失败 {stats['failed']} 个，"
          f"请求 {stats['requests']} 次{Style.RESET_ALL}")
    return stats


# --------------------------------------------------------------------------
# 整体同步
# --------------------------------------------------------------------------

def sync_all(conn, categories=None, interval="1h", start=None, end=None, symbols=None,
             min_quote_volume=0, force_metadata=False, update_progress=None,
             should_cancel=None, workers=SYNC_WORKERS, client=None):
    """一次完整同步：币池（按需）→ 24 小时行情 → K 线。"""
    categories = list(categories or db.CATEGORIES)
    client = client or BinanceClient()
    log_id = start_log(conn, "sync", categories)
    stats = {"rows": 0, "requests": 0, "failed": 0, "cancelled": False}
    try:
        if force_metadata or _metadata_is_stale(conn):
            if update_progress:
                update_progress(done=0, total=0, rows=0, message="同步币池（exchangeInfo）…")
            sync_symbols(conn, client)
        if update_progress:
            update_progress(done=0, total=0, rows=0, message="同步 24 小时行情…")
        sync_ticker(conn, client)
        if should_cancel and should_cancel():
            stats["cancelled"] = True
        else:
            kline = sync_klines(conn, client, interval=interval, categories=categories,
                                start=start, end=end, symbols=symbols,
                                min_quote_volume=min_quote_volume,
                                update_progress=update_progress, should_cancel=should_cancel,
                                workers=workers)
            stats.update({k: kline[k] for k in ("rows", "failed", "cancelled", "up_to_date",
                                                  "symbols", "used_weight")})
        stats["requests"] = client.requests
        stats["message"] = (f"{stats.get('up_to_date', 0)} 个已是最新未请求，"
                            f"本分钟权重 {client.used_weight}/2400")
        finish_log(conn, log_id, "cancelled" if stats["cancelled"] else "completed", stats)
        return stats
    except Exception as error:
        stats["requests"] = client.requests
        stats["message"] = str(error)
        finish_log(conn, log_id, "failed", stats)
        raise


# --------------------------------------------------------------------------
# 清理
# --------------------------------------------------------------------------

def cleanup(conn, keep_days=RETENTION_DAYS, interval="1h", categories=None, dry_run=True):
    """删除保留期之外的 K 线。dry_run=True 只统计不删。"""
    categories = list(categories or db.CATEGORIES)
    cutoff = now_ms() - keep_days * DAY_MS
    result = {"cutoff": format_beijing(cutoff), "dry_run": dry_run, "categories": {}, "total": 0}
    for category in categories:
        table = db.kline_table(interval, category)
        if dry_run:
            count = conn.execute(
                f'SELECT COUNT(*) FROM {table} WHERE "open_time" < ?', (cutoff,)).fetchone()[0]
        else:
            count = conn.execute(f'DELETE FROM {table} WHERE "open_time" < ?', (cutoff,)).rowcount
        result["categories"][category] = count
        result["total"] += count
    if not dry_run:
        conn.commit()
        log_id = start_log(conn, "cleanup", categories)
        finish_log(conn, log_id, "completed", {"rows": result["total"]})
    return result


def vacuum(conn):
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    before = os.path.getsize(path)
    conn.execute("VACUUM")
    after = os.path.getsize(path)
    return {"before": before, "after": after, "freed": before - after}


__all__ = ["sync_all", "sync_symbols", "sync_ticker", "sync_klines", "plan_kline_tasks",
           "fetch_symbol_klines", "cleanup", "vacuum", "recent_logs", "RETENTION_DAYS",
           "beijing_day_start_ms", "beijing_day_end_ms", "format_beijing", "last_closed_open"]
