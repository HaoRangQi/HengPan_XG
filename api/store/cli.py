"""
本地数据仓库的命令行入口。数据管理页做好之前，用它同步和查看。

    python -m api.store.cli status
    python -m api.store.cli sync                    # 三大板块，60 分钟线
    python -m api.store.cli sync --boards sz_gem    # 只同步创业板
    python -m api.store.cli sync --limit 50         # 只同步前 50 只，用于试跑
    python -m api.store.cli cleanup --keep-days 60  # 预览要删多少
    python -m api.store.cli cleanup --keep-days 60 --apply
"""
import argparse
import sys

from colorama import Fore, Style

from . import db, sync


def cmd_status(conn, args):
    print(f"{Fore.CYAN}数据库：{db.DB_PATH}{Style.RESET_ALL}")
    for board in db.KLINE_BOARDS:
        info = db.board_stats(conn, args.frequency, board)
        if info["rows"]:
            print(f"  {info['label']:<6} {info['rows']:>9,} 根 / {info['codes']:>5} 只  "
                  f"{info['first_date']} ~ {info['last_date']}")
        else:
            print(f"  {info['label']:<6} {Fore.YELLOW}（空）{Style.RESET_ALL}")
    total = conn.execute("SELECT COUNT(*) FROM stock_basic").fetchone()[0]
    days = db.trading_days(conn)
    print(f"  股票池 {total} 只，交易日历 {len(days)} 天"
          + (f"（{days[0]} ~ {days[-1]}）" if days else ""))
    for log in sync.recent_logs(conn, 5):
        print(f"  [{log['status']}] {log['action']} {log['started_at']} "
              f"请求 {log['requests']} 写入 {log['rows']} 失败 {log['failed']} "
              f"{log['message'] or ''}")


def cmd_sync(conn, args):
    boards = args.boards or list(db.DEFAULT_BOARDS)
    if args.limit:
        # 试跑：只同步前若干只，验证链路通不通，不打满请求量
        sync.sync_trade_calendar(conn)
        if not db.stock_list(conn, boards):
            sync.sync_stock_basic(conn)
            sync.sync_stock_industry(conn)
        end_date = sync.resolve_end_date(conn)
        codes = [s["code"] for s in db.stock_list(conn, boards)][:args.limit]
        print(f"{Fore.YELLOW}试跑模式：只同步 {len(codes)} 只{Style.RESET_ALL}")
        stats = _sync_subset(conn, codes, args.frequency, end_date)
    else:
        stats = sync.sync_all(conn, boards=boards, frequency=args.frequency,
                              force_metadata=args.force_metadata, workers=args.workers,
                              update_progress=_print_progress)
    print(f"{Fore.GREEN}写入 {stats['rows']} 根，请求 {stats['requests']} 次，"
          f"失败 {stats['failed']} 只{Style.RESET_ALL}")


def _sync_subset(conn, codes, frequency, end_date):
    """试跑用：串行拉指定的几只，不开进程池。"""
    from ..data_fetcher import baostock_login
    baostock_login()
    stats = {"rows": 0, "requests": 0, "failed": 0}
    for code in codes:
        board = db.board_of(code)
        start = sync.plan_start_dates(conn, frequency, board, [code], end_date)[code]
        stats["requests"] += 1
        try:
            rows = sync.fetch_kline_rows(code, start, end_date, frequency)
        except Exception as error:
            stats["failed"] += 1
            print(f"{Fore.RED}{code}: {error}{Style.RESET_ALL}")
            continue
        db.upsert(conn, db.kline_table(frequency, board), db.MINUTE_COLUMNS, rows)
        stats["rows"] += len(rows)
        print(f"  {code} {start}~{end_date} {len(rows)} 根")
    conn.commit()
    return stats


def _print_progress(done, total, rows, message):
    print(f"  {message}")


def cmd_cleanup(conn, args):
    result = sync.cleanup(conn, keep_days=args.keep_days, frequency=args.frequency,
                          dry_run=not args.apply)
    action = "已删除" if args.apply else "将删除"
    print(f"{action} {args.keep_days} 天前（{result['cutoff']} 之前）的数据：")
    for board, count in result["boards"].items():
        print(f"  {db.BOARD_LABELS[board]:<6} {count:>9,} 根")
    print(f"  合计 {result['total']:,} 根")
    if not args.apply:
        print(f"{Fore.YELLOW}这是预览，加 --apply 才会真的删除{Style.RESET_ALL}")


def cmd_vacuum(conn, args):
    result = sync.vacuum(conn)
    print(f"压缩完成：{result['before'] / 1e6:.0f} MB → {result['after'] / 1e6:.0f} MB，"
          f"回收 {result['freed'] / 1e6:.0f} MB")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="api.store.cli", description="本地 K 线数据仓库")
    parser.add_argument("--db", help="数据库路径，默认 api/data/market.db")
    parser.add_argument("--frequency", default="60", choices=db.FREQUENCIES, help="K 线周期")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="查看本地数据概览")

    p_sync = sub.add_parser("sync", help="增量同步")
    p_sync.add_argument("--boards", nargs="*", choices=db.KLINE_BOARDS,
                        help=f"要同步的板块，默认 {' '.join(db.DEFAULT_BOARDS)}")
    p_sync.add_argument("--workers", type=int, default=sync.SYNC_WORKERS, help="并发进程数")
    p_sync.add_argument("--limit", type=int, help="只同步前 N 只（试跑）")
    p_sync.add_argument("--force-metadata", action="store_true", help="强制重拉股票池和行业")

    p_clean = sub.add_parser("cleanup", help="清理过期数据")
    p_clean.add_argument("--keep-days", type=int, default=sync.RETENTION_DAYS, help="保留天数")
    p_clean.add_argument("--apply", action="store_true", help="真的删除，默认只预览")

    sub.add_parser("vacuum", help="压缩数据库，回收空间")

    args = parser.parse_args(argv)
    handlers = {"status": cmd_status, "sync": cmd_sync,
                "cleanup": cmd_cleanup, "vacuum": cmd_vacuum}
    with db.open_db(args.db) as conn:
        try:
            handlers[args.command](conn, args)
        except (ConnectionError, ValueError) as error:
            print(f"{Fore.RED}{error}{Style.RESET_ALL}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
