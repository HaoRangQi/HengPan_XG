"""
同步任务：从 Baostock 增量拉取数据写入本地库。

只有这个模块会联网。扫描和分析全部读本地，不再发任何请求。
60 分钟线没有按日期批量取的接口，只能逐只请求；股票池、行业、交易日历、复权因子
都有批量接口，每次同步各 1 次请求。
"""
import os
import socket
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from datetime import datetime, timedelta

import baostock as bs
from colorama import Fore, Style

from ..data_fetcher import (BaostockBlacklisted, baostock_login, is_blacklist_error,
                            _fetch_metadata_with_retry)
from ..hengpan.fetcher import query_kline
from ..process_pool import close_process_pool
from . import db

# 本地保留多少天的 60 分钟线。约 40 个交易日、160 根，够 lookback 150 以内的规则回验。
RETENTION_DAYS = 60
# 子进程 socket 超时（秒）。baostock 建连接时不设超时，服务端不响应时 recv 会一直等。
SOCKET_TIMEOUT = 30
# 同步并发进程数。比扫描的 5 个保守，降低触发封禁的概率。
SYNC_WORKERS = 3
# 攒够这么多只就批量写一次库
WRITE_BATCH = 200
# 一只都没成功、却已连续失败这么多只时，认为数据源整体不可用，提前中止
ABORT_AFTER_FAILURES = 50
# 股票池和行业分类隔这么多天才重新拉一次
METADATA_MAX_AGE_DAYS = 7
# 每个交易日最后一根分钟线的时刻（time 字段第 9~14 位）。本地有截止日这一根，说明这只股票已是最新。
LAST_BAR_CLOCK = "150000"
# 正式同步前最多用几只股票探测数据源。取几只大盘股，避免碰巧探到停牌股误判「没更新」。
PROBE_LIMIT = 3
PROBE_CODES = ("sh.600000", "sz.000001", "sh.601398", "sz.000002", "sh.600519")
# 待同步股票不超过这么多只时不探测，直接拉：探测省不了几次请求，
# 反而可能因为只指定了几只停牌股而误判成「数据源没更新」
PROBE_MIN_BATCH = 50

MINUTE_FIELDS = ",".join(db.MINUTE_COLUMNS)


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _date_of(time_value):
    """把 time 字段（YYYYMMDDHHMMSSsss）还原成 YYYY-MM-DD。"""
    text = str(time_value)
    return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"


def _rows_of(frame, columns):
    """DataFrame 按给定列顺序转成元组列表，缺列补空串。"""
    if frame is None or frame.empty:
        return []
    for column in columns:
        if column not in frame:
            frame[column] = ""
    return [tuple("" if value is None else str(value) for value in row)
            for row in frame[list(columns)].itertuples(index=False)]


# --------------------------------------------------------------------------
# 元数据：交易日历 / 股票池 / 行业分类 / 复权因子
# --------------------------------------------------------------------------

def sync_trade_calendar(conn, start=None, end=None):
    """交易日历。默认拉去年初到明年初，覆盖跨年。1 次请求。"""
    year = datetime.now().year
    start = start or f"{year - 1}-01-01"
    end = end or f"{year + 1}-01-01"
    frame = _fetch_metadata_with_retry(
        "trade dates", lambda: bs.query_trade_dates(start_date=start, end_date=end))
    rows = _rows_of(frame, ("calendar_date", "is_trading_day"))
    written = db.upsert(conn, "trade_calendar", ("calendar_date", "is_trading_day"), rows)
    conn.commit()
    print(f"{Fore.GREEN}交易日历：{written} 天{Style.RESET_ALL}")
    return written


def sync_stock_basic(conn):
    """证券基本资料。只写 type='1' 的股票，顺带算出 board。1 次请求。"""
    frame = _fetch_metadata_with_retry("stock basics", bs.query_stock_basic)
    columns = ("code", "code_name", "ipoDate", "outDate", "type", "status")
    now = datetime.now().isoformat(timespec="seconds")
    rows = []
    for row in _rows_of(frame, columns):
        if row[4] != "1":          # type：1 股票，排除指数 / 可转债 / ETF
            continue
        board = db.board_of(row[0])
        if board not in db.KLINE_BOARDS:   # 北交所 Baostock 不支持，代码段不认识的也跳过
            continue
        rows.append(row + (board, now))
    written = db.upsert(conn, "stock_basic", columns + ("board", "updated_at"), rows)
    conn.commit()
    print(f"{Fore.GREEN}股票池：{written} 只{Style.RESET_ALL}")
    return written


def sync_stock_industry(conn):
    """行业分类。官方每周一更新。1 次请求。"""
    frame = _fetch_metadata_with_retry("industry data", bs.query_stock_industry)
    columns = ("code", "code_name", "industry", "industryClassification", "updateDate")
    written = db.upsert(conn, "stock_industry", columns, _rows_of(frame, columns))
    conn.commit()
    print(f"{Fore.GREEN}行业分类：{written} 条{Style.RESET_ALL}")
    return written


ADJUST_COLUMNS = ("code", "dividOperateDate", "foreAdjustFactor",
                  "backAdjustFactor", "adjustFactor")


def sync_adjust_factor_by_day(conn, days, should_cancel=None):
    """
    按交易日增量取复权因子，每天 1 次请求，只返回当天除权的几十只股票。

    注意：这样取到的 foreAdjustFactor 恒为 1.0，和全量查询的值互相矛盾，
    所以读取层只认 backAdjustFactor（累计值，不随后续除权变化）。
    """
    written = requests = 0
    for day in days:
        if should_cancel and should_cancel():
            break
        frame = _fetch_metadata_with_retry(
            f"adjust factor {day}", lambda d=day: bs.query_daily_adjust_factor(date=d),
            allow_empty=True)
        requests += 1
        written += db.upsert(conn, "adjust_factor", ADJUST_COLUMNS,
                             _rows_of(frame, ADJUST_COLUMNS))
        # 即使当天没有除权记录，也要推进游标，避免下次再次请求同一天。
        db.set_meta(conn, "adjust_factor_daily_through", day)
    conn.commit()
    if written:
        print(f"{Fore.GREEN}复权因子：{written} 条（{requests} 个交易日）{Style.RESET_ALL}")
    return written, requests


def fetch_adjust_factor(code):
    """取单只股票的完整复权因子历史，在子进程里运行。首次初始化用。"""
    frame = _fetch_metadata_with_retry(
        f"adjust factor {code}",
        lambda: bs.query_adjust_factor(code=code, start_date="2015-01-01", end_date=_today()),
        allow_empty=True)
    return _rows_of(frame, ADJUST_COLUMNS)


def sync_initial_adjust_factors(conn, boards=None, update_progress=None,
                                should_cancel=None, workers=SYNC_WORKERS):
    """首次逐只拉完整复权因子历史；按证券记录完成状态，可中断续传。"""
    boards = list(boards or db.DEFAULT_BOARDS)
    stocks = db.stock_list(conn, boards)
    completed = {row[0] for row in conn.execute("SELECT code FROM adjust_factor_sync")}
    codes = [stock["code"] for stock in stocks if stock["code"] not in completed]
    code_boards = {stock["code"]: stock["board"] for stock in stocks}
    failed_boards = set()
    stats = {"rows": 0, "requests": 0, "failed": 0, "cancelled": False}
    successful = 0
    if not stocks:
        raise ValueError("本地股票池为空，请先同步股票池")
    if not codes:
        for board in boards:
            db.set_meta(conn, f"adjust_factor_history:{board}", "complete")
        return stats

    executor = ProcessPoolExecutor(max_workers=workers, initializer=_init_worker)
    pending = {}
    next_index = 0
    window = max(1, workers * 2)

    def submit_window():
        nonlocal next_index
        while next_index < len(codes) and len(pending) < window:
            if should_cancel and should_cancel():
                return False
            code = codes[next_index]
            pending[executor.submit(fetch_adjust_factor, code)] = code
            next_index += 1
        return True

    aborted = False
    try:
        if not submit_window():
            stats["cancelled"] = True
        while pending:
            ready, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
            for future in ready:
                code = pending.pop(future)
                if should_cancel and should_cancel():
                    stats["cancelled"] = True
                    break
                stats["requests"] += 1
                try:
                    rows = future.result()
                except BaostockBlacklisted:
                    raise
                except Exception as error:
                    stats["failed"] += 1
                    failed_boards.add(code_boards[code])
                    print(f"{Fore.RED}复权因子失败 {code}: {error}{Style.RESET_ALL}")
                    if successful == 0 and stats["failed"] >= ABORT_AFTER_FAILURES:
                        raise ConnectionError(
                            f"连续 {ABORT_AFTER_FAILURES} 只复权因子获取失败，数据源可能不可用。最近错误：{error}")
                    continue
                successful += 1
                stats["rows"] += db.upsert(conn, "adjust_factor", ADJUST_COLUMNS, rows)
                conn.execute(
                    "INSERT INTO adjust_factor_sync (code, completed_at) VALUES (?,?) "
                    "ON CONFLICT(code) DO UPDATE SET completed_at=excluded.completed_at",
                    (code, datetime.now().isoformat(timespec="seconds")))
                completed.add(code)
                if stats["requests"] % 100 == 0:
                    conn.commit()
                    if update_progress:
                        update_progress(done=stats["requests"], total=len(codes), rows=stats["rows"],
                                        message=f"初始化复权因子 {stats['requests']}/{len(codes)}")
            if stats["cancelled"] or not submit_window():
                stats["cancelled"] = True
                break
    except Exception:
        aborted = True
        raise
    finally:
        close_process_pool(executor, pending, force=aborted or stats["cancelled"] or bool(pending))
        conn.commit()

    for board in boards:
        board_codes = {stock["code"] for stock in stocks if stock["board"] == board}
        if board not in failed_boards and board_codes.issubset(completed):
            db.set_meta(conn, f"adjust_factor_history:{board}", "complete")
    return stats


# --------------------------------------------------------------------------
# K 线
# --------------------------------------------------------------------------

def _init_worker():
    """子进程初始化：先设 socket 超时，卡住的请求才会抛异常并走重试；再登录。"""
    socket.setdefaulttimeout(SOCKET_TIMEOUT)
    baostock_login()


def fetch_kline_rows(code, start_date, end_date, frequency, retry_attempts=2):
    """在子进程里运行：取一只股票的原始 K 线，不做任何清洗，原样返回。"""
    frame = query_kline(code, MINUTE_FIELDS, start_date, end_date,
                        frequency=frequency, adjustflag="3",
                        retry_attempts=retry_attempts)
    return _rows_of(frame, db.MINUTE_COLUMNS)


def resolve_end_date(conn, end=None):
    """
    同步截止日：交易日历上不晚于 end（默认今天）的最后一个交易日。

    用户选的结束日期落在周末或节假日时，自动退到它之前最近的交易日；
    选了未来的日期也按今天算，数据源不会有未来的数据。
    """
    limit = min(end, _today()) if end else _today()
    days = db.trading_days(conn, end=limit)
    if not days:
        raise ValueError("本地交易日历为空，请先同步交易日历")
    return days[-1]


def _is_complete(last_time, end_date):
    """本地最后一根是不是截止日收盘那根（15:00）。是的话这只股票已经是最新，不用再请求。"""
    return bool(last_time) and str(last_time)[:8] == end_date.replace("-", "") \
        and str(last_time)[8:14] == LAST_BAR_CLOCK


def plan_start_dates(conn, frequency, board, codes, end_date, start_date=None):
    """
    每只股票的取数起点。返回的字典里只包含需要请求的股票。

    指定了 start_date（补历史区间）→ 所有股票都从该日拉，不看本地已有到哪
    未指定（日常增量）：
      已有截止日 15:00 那根 → 已是最新，不在返回结果里，不发请求
      有本地数据 → 从最后一根所在那天重新拉（当天可能只存了上午的，重拉覆盖）
      没有数据   → 从保留期开头拉
    """
    if start_date:
        return {code: start_date for code in codes}
    floor = (datetime.strptime(end_date, "%Y-%m-%d")
             - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
    known = db.latest_times(conn, frequency, board)
    plan = {}
    for code in codes:
        last = known.get(code)
        if _is_complete(last, end_date):
            continue
        plan[code] = max(_date_of(last), floor) if last else floor
    return plan


def _probe_source(conn, tasks, frequency, end_date, stats, retry_attempts=2):
    """
    正式开进程池前，先在主进程拉 1~PROBE_LIMIT 只股票，确认数据源已有截止日的数据。

    探测用的就是这几只股票本来的取数任务，拉回来的数据照常写库，不多花请求。
    返回去掉已探测股票后剩下的任务。都拿不到截止日的数据时抛错停止：
    多半是当天数据还没入库，这时让几千只股票逐只去试只会白白消耗请求额度。
    """
    # 优先挑大盘股，碰到停牌股的概率低；它们不在本次任务里就按原顺序取前几只
    priority = {code: rank for rank, code in enumerate(PROBE_CODES)}
    candidates = sorted(range(len(tasks)),
                        key=lambda i: priority.get(tasks[i][1], len(priority)))[:PROBE_LIMIT]
    probed = set()
    for index in candidates:
        board, code, start = tasks[index]
        probed.add(index)
        stats["requests"] += 1
        stats["probe"] += 1
        try:
            rows = fetch_kline_rows(code, start, end_date, frequency, retry_attempts)
        except BaostockBlacklisted as error:
            raise ConnectionError(
                f"Baostock 已将本机列入黑名单，同步中止。解封后再点同步会从断点继续。原始错误：{error}")
        except Exception as error:
            stats["failed"] += 1
            print(f"{Fore.YELLOW}探测失败 {code}: {error}{Style.RESET_ALL}")
            continue
        if rows:
            db.upsert(conn, db.kline_table(frequency, board), db.MINUTE_COLUMNS, rows)
            conn.commit()
            stats["rows"] += len(rows)
        if any(row[0] == end_date for row in rows):   # row[0] 是 date 字段
            print(f"{Fore.GREEN}探测通过：{code} 已有 {end_date} 的数据{Style.RESET_ALL}")
            return [task for i, task in enumerate(tasks) if i not in probed]
    raise ConnectionError(
        f"探测了 {len(probed)} 只股票，Baostock 都还没有 {end_date} 的 {frequency} 分钟数据，"
        f"多半是当天数据尚未入库，请晚些再同步。本次只发了 {stats['requests']} 次请求，"
        f"其余 {len(tasks) - len(probed)} 只没有请求。")


def sync_kline(conn, boards=None, frequency="60", end_date=None, start_date=None,
               codes=None, update_progress=None, should_cancel=None, workers=SYNC_WORKERS,
               retry_attempts=2):
    """
    逐只拉取 K 线写入本地库。

    start_date：指定则补这个区间（所有股票都从该日拉）；留空则按本地进度增量
    codes：只同步这几只，留空为所选板块的全部股票
    update_progress(done, total, rows, message)：进度回调
    should_cancel()：返回 True 时停止，已写入的数据保留

    返回 {"rows", "requests", "failed", "cancelled", "start_date", "end_date", "boards"}。
    中途取消或失败都不影响已写入的数据，下次同步会从断点接着拉。
    """
    boards = list(boards or db.DEFAULT_BOARDS)
    end_date = end_date or resolve_end_date(conn)
    if start_date and start_date > end_date:
        raise ValueError(f"起始日期 {start_date} 不能晚于结束日期 {end_date}")
    stocks = db.stock_list(conn, boards)
    if codes:
        wanted = set(codes)
        stocks = [s for s in stocks if s["code"] in wanted]
        if not stocks:
            raise ValueError("指定的股票都不在所选板块的股票池里")
    if not stocks:
        raise ValueError("本地股票池为空，请先同步股票池")

    # 按板块分组，各自算取数起点；日常增量时，已是最新的股票不在计划里，不发请求
    tasks = []
    for board in boards:
        board_codes = [s["code"] for s in stocks if s["board"] == board]
        if not board_codes:
            continue
        starts = plan_start_dates(conn, frequency, board, board_codes, end_date, start_date)
        tasks += [(board, code, starts[code]) for code in board_codes if code in starts]

    stats = {"rows": 0, "requests": 0, "failed": 0, "cancelled": False,
             "start_date": start_date, "end_date": end_date, "boards": boards, "empty": 0,
             "up_to_date": len(stocks) - len(tasks), "probe": 0}
    print(f"{Fore.CYAN}======================================{Style.RESET_ALL}")
    print(f"{Fore.CYAN}同步 {frequency} 分钟线{Style.RESET_ALL}")
    print(f"  - 板块: {Fore.GREEN}{'/'.join(db.BOARD_LABELS[b] for b in boards)}{Style.RESET_ALL}")
    print(f"  - 区间: {Fore.GREEN}{start_date or '按本地进度增量'} ~ {end_date}{Style.RESET_ALL}")
    print(f"  - 股票: {Fore.GREEN}{len(tasks)}{Style.RESET_ALL} 只待同步，"
          f"{stats['up_to_date']} 只已是最新，{workers} 个进程")
    print(f"{Fore.CYAN}======================================{Style.RESET_ALL}")

    if not tasks:
        message = f"全部 {len(stocks)} 只已是最新（截止 {end_date}），没有发请求"
        print(f"{Fore.GREEN}{message}{Style.RESET_ALL}")
        if update_progress:
            update_progress(done=0, total=0, rows=0, message=message)
        return stats

    # 批量较大时先探测：数据源没更新就只花几次请求，而不是让几千只股票逐只去试
    if len(tasks) > PROBE_MIN_BATCH:
        if update_progress:
            update_progress(done=0, total=len(tasks), rows=0,
                            message=f"正在确认数据源是否已有 {end_date} 的数据…")
        tasks = _probe_source(conn, tasks, frequency, end_date, stats, retry_attempts)

    total = len(tasks)
    buffers = {board: [] for board in boards}
    done = 0
    executor = ProcessPoolExecutor(max_workers=workers, initializer=_init_worker)
    pending = {}
    next_index = 0
    window = max(1, workers * 2)

    def flush(board=None):
        """把攒着的行写库。只在主进程执行，SQLite 同一时刻只能有一个写入者。"""
        for name in ([board] if board else list(buffers)):
            rows = buffers[name]
            if rows:
                db.upsert(conn, db.kline_table(frequency, name), db.MINUTE_COLUMNS, rows)
                buffers[name] = []
        conn.commit()

    def submit_window():
        nonlocal next_index
        while next_index < total and len(pending) < window:
            if should_cancel and should_cancel():
                return False
            board, code, start = tasks[next_index]
            pending[executor.submit(fetch_kline_rows, code, start, end_date,
                                    frequency, retry_attempts)] = (board, code)
            next_index += 1
        return True

    def process(future, board, code):
        nonlocal done
        done += 1
        stats["requests"] += 1
        try:
            rows = future.result()
        except BaostockBlacklisted as error:
            raise ConnectionError(
                f"Baostock 已将本机列入黑名单，同步中止。已写入的数据保留，"
                f"解封后再点同步会从断点继续。原始错误：{error}")
        except Exception as error:
            stats["failed"] += 1
            print(f"{Fore.RED}取数失败 {code}: {error}{Style.RESET_ALL}")
            # 一只都没成功却已连续失败很多只，通常是数据源整体不可用
            if stats["rows"] == 0 and stats["failed"] >= ABORT_AFTER_FAILURES:
                raise ConnectionError(
                    f"连续 {ABORT_AFTER_FAILURES} 只取数失败，数据源可能不可用。最近错误：{error}")
            return

        if rows:
            buffers[board] += rows
            stats["rows"] += len(rows)
            if len(buffers[board]) >= WRITE_BATCH:
                flush(board)
        else:
            stats["empty"] += 1

        if update_progress and (done % 20 == 0 or done == total):
            update_progress(done=done, total=total, rows=stats["rows"],
                            message=f"已同步 {done}/{total} 只，写入 {stats['rows']} 根 K 线")

    aborted = False
    try:
        if not submit_window():
            stats["cancelled"] = True
        while pending:
            ready, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
            for future in ready:
                board, code = pending.pop(future)
                if should_cancel and should_cancel():
                    stats["cancelled"] = True
                    break
                process(future, board, code)
            if stats["cancelled"] or not submit_window():
                stats["cancelled"] = True
                print(f"{Fore.YELLOW}已请求停止，同步中断（{done}/{total}）{Style.RESET_ALL}")
                break
    except Exception:
        aborted = True
        raise
    finally:
        close_process_pool(executor, pending, force=aborted or stats["cancelled"] or bool(pending))
        flush()

    # 全部返回空且一条都没失败 → 数据源当天还没入库，不是本地的问题
    if stats["rows"] == 0 and stats["empty"] >= min(total, ABORT_AFTER_FAILURES) \
            and not stats["failed"] and not stats["cancelled"]:
        raise ConnectionError(
            f"{end_date} 是交易日但所有股票都没返回数据，Baostock 当天的数据可能还没入库，请稍后再试")

    print(f"{Fore.GREEN}同步完成：写入 {stats['rows']} 根，失败 {stats['failed']} 只，"
          f"请求 {stats['requests']} 次{Style.RESET_ALL}")
    return stats


# --------------------------------------------------------------------------
# 整体同步
# --------------------------------------------------------------------------

def _metadata_is_stale(conn):
    row = conn.execute("SELECT MAX(updated_at) FROM stock_basic").fetchone()
    if not row or not row[0]:
        return True
    age = datetime.now() - datetime.fromisoformat(row[0])
    return age > timedelta(days=METADATA_MAX_AGE_DAYS)


def _calendar_is_stale(conn):
    """本地交易日历还没覆盖到今天（或为空）时才需要重拉。每次拉的是去年初到明年初。"""
    row = conn.execute("SELECT MAX(calendar_date) FROM trade_calendar").fetchone()
    return not row or not row[0] or row[0] < _today()


def sync_all(conn, boards=None, frequency="60", force_metadata=False,
             start=None, end=None, codes=None,
             update_progress=None, should_cancel=None, workers=SYNC_WORKERS):
    """
    一次完整同步：交易日历 → 股票池 → 行业 → 复权因子 → K 线。

    start / end：K 线的取数区间。start 留空表示按本地进度增量（日常用法）；
                 指定 start 则补这个区间的历史，所有股票都从该日重新拉。
    codes：只同步指定的几只股票，留空为所选板块全部。

    股票池和行业隔 7 天才重拉一次，平时每次同步只花 1（日历）+ N（复权因子）+ 股票数 次请求。
    """
    boards = list(boards or db.DEFAULT_BOARDS)
    log_id = start_log(conn, "sync", boards)
    stats = {"rows": 0, "requests": 0, "failed": 0, "cancelled": False}

    def stop_if_requested(message="同步已停止"):
        if not (should_cancel and should_cancel()):
            return False
        stats["cancelled"] = True
        stats["message"] = message
        if update_progress:
            update_progress(done=0, total=0, rows=stats["rows"], message=message)
        finish_log(conn, log_id, "cancelled", stats)
        return True

    try:
        if stop_if_requested():
            return stats
        # 交易日历是静态数据，本地已覆盖到今天就不再请求
        if _calendar_is_stale(conn):
            if update_progress:
                update_progress(done=0, total=0, rows=0, message="同步交易日历…")
            sync_trade_calendar(conn)
            stats["requests"] += 1
            if stop_if_requested():
                return stats

        if force_metadata or _metadata_is_stale(conn):
            if update_progress:
                update_progress(done=0, total=0, rows=0, message="同步股票池和行业分类…")
            sync_stock_basic(conn)
            sync_stock_industry(conn)
            stats["requests"] += 2
            if stop_if_requested():
                return stats

        stock_codes = {stock["code"] for stock in db.stock_list(conn, boards)}
        factor_codes = {row[0] for row in conn.execute("SELECT code FROM adjust_factor_sync")}
        if not stock_codes.issubset(factor_codes):
            if update_progress:
                update_progress(done=0, total=0, rows=0, message="首次初始化完整复权因子…")
            factor_init = sync_initial_adjust_factors(
                conn, boards=boards, update_progress=update_progress,
                should_cancel=should_cancel, workers=workers)
            stats["requests"] += factor_init["requests"]
            stats["failed"] += factor_init["failed"]
            if factor_init["cancelled"]:
                stats["cancelled"] = True
                finish_log(conn, log_id, "cancelled", stats)
                return stats
        if stop_if_requested():
            return stats

        end_date = resolve_end_date(conn, end)
        if update_progress:
            update_progress(done=0, total=0, rows=0, message="同步复权因子…")
        _, factor_requests = sync_adjust_factor_by_day(
            conn, _pending_factor_days(conn, end_date), should_cancel=should_cancel)
        stats["requests"] += factor_requests
        if stop_if_requested():
            return stats

        kline = sync_kline(conn, boards=boards, frequency=frequency, end_date=end_date,
                           start_date=start, codes=codes,
                           update_progress=update_progress, should_cancel=should_cancel,
                           workers=workers)
        stats["rows"] = kline["rows"]
        stats["failed"] += kline["failed"]
        stats["cancelled"] = kline["cancelled"]
        stats["requests"] += kline["requests"]
        stats["start_date"] = kline["start_date"]
        stats["end_date"] = end_date
        stats["up_to_date"] = kline["up_to_date"]
        stats["message"] = (f"截止 {end_date}：{kline['up_to_date']} 只已是最新未请求，"
                            f"探测 {kline['probe']} 次")
        finish_log(conn, log_id, "cancelled" if kline["cancelled"] else "completed", stats)
        return stats
    except Exception as error:
        stats["message"] = str(error)
        finish_log(conn, log_id, "failed", stats)
        raise


def _pending_factor_days(conn, end_date):
    """还没取过复权因子的交易日。首次同步只回溯保留期，避免一次拉几百天。"""
    floor = (datetime.strptime(end_date, "%Y-%m-%d")
             - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
    through = db.get_meta(conn, "adjust_factor_daily_through")
    start = max(through, floor) if through else floor
    days = db.trading_days(conn, start=start, end=end_date)
    return [day for day in days if not through or day > through]


# --------------------------------------------------------------------------
# 同步日志
# --------------------------------------------------------------------------

def start_log(conn, action, boards):
    cursor = conn.execute(
        "INSERT INTO sync_log (action, boards, started_at, status) VALUES (?,?,?,?)",
        (action, ",".join(boards or []), datetime.now().isoformat(timespec="seconds"), "running"))
    conn.commit()
    return cursor.lastrowid


def finish_log(conn, log_id, status, stats):
    conn.execute(
        "UPDATE sync_log SET finished_at=?, status=?, requests=?, rows=?, failed=?, message=? "
        "WHERE id=?",
        (datetime.now().isoformat(timespec="seconds"), status, stats.get("requests", 0),
         stats.get("rows", 0), stats.get("failed", 0), stats.get("message"), log_id))
    conn.commit()


def recent_logs(conn, limit=20):
    rows = conn.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT ?", (limit,))
    return [dict(row) for row in rows]


# --------------------------------------------------------------------------
# 清理
# --------------------------------------------------------------------------

def cleanup(conn, keep_days=RETENTION_DAYS, frequency="60", boards=None, dry_run=True):
    """删除保留期之外的 K 线。dry_run=True 只统计不删，供页面先预览。"""
    boards = list(boards or db.KLINE_BOARDS)
    cutoff = (datetime.now() - timedelta(days=keep_days)).strftime("%Y-%m-%d")
    result = {"cutoff": cutoff, "dry_run": dry_run, "boards": {}, "total": 0}
    for board in boards:
        table = db.kline_table(frequency, board)
        if dry_run:
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE date < ?", (cutoff,)).fetchone()[0]
        else:
            count = conn.execute(f"DELETE FROM {table} WHERE date < ?", (cutoff,)).rowcount
        result["boards"][board] = count
        result["total"] += count
    if not dry_run:
        conn.commit()
        log_id = start_log(conn, "cleanup", boards)
        finish_log(conn, log_id, "completed", {"rows": result["total"]})
    return result


def vacuum(conn):
    """回收删除后的空闲空间。文件较大时耗时较久。"""
    before = os.path.getsize(conn.execute("PRAGMA database_list").fetchone()[2])
    conn.execute("VACUUM")
    after = os.path.getsize(conn.execute("PRAGMA database_list").fetchone()[2])
    return {"before": before, "after": after, "freed": before - after}
