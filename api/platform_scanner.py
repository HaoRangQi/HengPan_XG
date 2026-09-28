"""
Platform Scanner module for scanning stocks for platform consolidation patterns.
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
import time
from datetime import datetime, timedelta
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, ThreadPoolExecutor, wait
from tqdm import tqdm
from colorama import Fore, Style

from .data_fetcher import fetch_kline_data, baostock_login
from .industry_filter import apply_industry_diversity_filter
from .config import ScanConfig

# Import analyzers
from .analyzers.price_analyzer import analyze_price
from .analyzers.volume_analyzer import analyze_volume
from .analyzers.combined_analyzer import analyze_stock
from .analyzers.fundamental_analyzer import analyze_fundamentals


# 代码前缀 → 板块。Baostock 的代码形如 sh.600000 / sz.300750 / bj.830799
BOARD_PREFIXES: Dict[str, List[str]] = {
    'sh_main': ['sh.600', 'sh.601', 'sh.603', 'sh.605'],  # 沪市主板
    'sh_star': ['sh.688', 'sh.689'],                      # 科创板
    'sz_main': ['sz.000', 'sz.001', 'sz.002', 'sz.003'],  # 深市主板（含原中小板）
    'sz_gem': ['sz.300', 'sz.301', 'sz.302'],             # 创业板
    'bj': ['bj.'],                                        # 北交所
}
# 板块 key 会被拼接成代码前缀元组，代码前缀做精确匹配
_MARKET_PREFIXES = {key: tuple(prefixes) for key, prefixes in BOARD_PREFIXES.items()}


class _ScanExecutorContext:
    """Executor context that does not re-wait after a cancellation request."""

    def __init__(self, executor_class, max_workers: int, initializer=baostock_login):
        self.executor_class = executor_class
        self.max_workers = max_workers
        self.initializer = initializer
        self.executor = None

    def __enter__(self):
        kwargs = {"max_workers": self.max_workers}
        if self.initializer is not None:
            kwargs["initializer"] = self.initializer
        self.executor = self.executor_class(**kwargs)
        return self.executor

    def __exit__(self, exc_type, exc_val, exc_tb):
        cancelled = bool(getattr(self.executor, "_scan_cancelled", False))
        self.executor.shutdown(wait=not cancelled, cancel_futures=cancelled)
        return False


def _iter_bounded_futures(executor, stock_list, submit, should_cancel,
                          max_in_flight):
    """Yield completed work while keeping cancellation from queueing the whole pool."""
    pending = {}
    stock_iter = iter(stock_list)

    def fill():
        while len(pending) < max_in_flight and not (should_cancel and should_cancel()):
            try:
                stock = next(stock_iter)
            except StopIteration:
                return
            pending[submit(stock)] = stock

    fill()
    cancelled = False
    try:
        while pending:
            if should_cancel and should_cancel():
                cancelled = True
                break
            completed, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
            for future in completed:
                stock = pending.pop(future)
                yield future, stock
                if should_cancel and should_cancel():
                    cancelled = True
                    break
                fill()
            if cancelled:
                break
    finally:
        if cancelled or (should_cancel and should_cancel()):
            executor._scan_cancelled = True
            for future in pending:
                future.cancel()


def select_markets(stock_list: List[Dict[str, Any]],
                   markets: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Narrow the stock pool to the requested boards.

    Args:
        stock_list: Full stock list
        markets: Board keys such as ['sh_main', 'sz_gem']; empty or None means all boards

    Returns:
        Filtered stock list
    """
    if not markets:
        return stock_list

    prefixes = tuple(p for key in markets for p in _MARKET_PREFIXES.get(key, ()))
    if not prefixes:
        return stock_list

    selected = [s for s in stock_list if s['code'].startswith(prefixes)]
    print(f"{Fore.CYAN}Market filter {markets}: "
          f"{len(selected)}/{len(stock_list)} stocks{Style.RESET_ALL}")
    return selected


def prepare_stock_list(stock_basics_df: pd.DataFrame,
                       industry_df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Prepare a list of stocks for scanning, excluding indices and merging industry data.

    Args:
        stock_basics_df: DataFrame containing stock basic information
        industry_df: DataFrame containing industry classification

    Returns:
        List of dictionaries with stock information
    """
    # Filter out indices (type=2) and non-active stocks (status=0)
    stock_list = []

    for _, row in stock_basics_df.iterrows():
        # Skip indices and inactive stocks
        if row['type'] == '2' or row['status'] == '0':
            continue

        stock_info = {
            'code': row['code'],
            'name': row['code_name'],
            'type': row['type'],
            'status': row['status'],
            'industry': '未知行业'  # Default value
        }

        # Add to list
        stock_list.append(stock_info)

    # Add industry information if available
    if not industry_df.empty:
        industry_dict = dict(zip(industry_df['code'], industry_df['industry']))
        for stock in stock_list:
            if stock['code'] in industry_dict:
                stock['industry'] = industry_dict[stock['code']]

    return stock_list


def scan_stocks(stock_list: List[Dict[str, Any]],
                config: ScanConfig,
                update_progress: Optional[callable] = None,
                should_cancel: Optional[callable] = None,
                on_found: Optional[callable] = None,
                frequency: str = "d",
                local_db_path: Optional[str] = None,
                end_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Scan stocks for platform consolidation patterns.

    Args:
        stock_list: List of stocks to scan
        config: Scan configuration
        update_progress: Optional callback for updating progress

    Args:
        should_cancel: 可选，返回 True 时停止扫描并保留已找到的结果
        on_found: 可选，每发现一只平台期股票就回调一次，用于边扫边出

    Returns:
        List of stocks that meet platform criteria
    """
    if frequency not in ("d", "60"):
        raise ValueError("frequency must be 'd' or '60'")
    use_local = bool(local_db_path)
    if use_local and frequency != "60":
        raise ValueError("local platform scans require 60-minute data")
    # Calculate date range. A trading day contains about four 60-minute bars;
    # include a generous weekend/holiday buffer so a 100-bar request has data.
    end_date = end_date or datetime.now().strftime('%Y-%m-%d')
    end_day = datetime.strptime(end_date, '%Y-%m-%d')
    # Use the maximum window size plus some buffer for the start date
    max_window = max(config.windows) if config.windows else 90
    calendar_days = (max_window * 2 if frequency == "d" else
                     max(30, int(max_window * 7 / 4 * 1.5)))
    start_date = (end_day - timedelta(days=calendar_days)
                  ).strftime('%Y-%m-%d')

    print(f"{Fore.CYAN}======================================{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Starting stock platform scan{Style.RESET_ALL}")
    print(f"{Fore.CYAN}======================================{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Scan parameters:{Style.RESET_ALL}")
    print(
        f"  - Date range: {Fore.GREEN}{start_date} to {end_date}{Style.RESET_ALL}")
    print(f"  - Windows: {Fore.GREEN}{config.windows}{Style.RESET_ALL}")
    print(
        f"  - Box threshold: {Fore.GREEN}{config.box_threshold}{Style.RESET_ALL}")
    print(
        f"  - MA diff threshold: {Fore.GREEN}{config.ma_diff_threshold}{Style.RESET_ALL}")
    print(
        f"  - Volatility threshold: {Fore.GREEN}{config.volatility_threshold}{Style.RESET_ALL}")

    # Print volume analysis parameters if enabled
    if config.use_volume_analysis:
        print(f"  - Volume analysis: {Fore.GREEN}Enabled{Style.RESET_ALL}")
        print(
            f"  - Volume change threshold: {Fore.GREEN}{config.volume_change_threshold}{Style.RESET_ALL}")
        print(
            f"  - Volume stability threshold: {Fore.GREEN}{config.volume_stability_threshold}{Style.RESET_ALL}")
        print(
            f"  - Volume increase threshold: {Fore.GREEN}{config.volume_increase_threshold}{Style.RESET_ALL}")
    else:
        print(f"  - Volume analysis: {Fore.YELLOW}Disabled{Style.RESET_ALL}")

    # Print window weights if enabled
    if config.use_window_weights:
        print(f"  - Window weights: {Fore.GREEN}Enabled{Style.RESET_ALL}")
        for window, weight in config.window_weights.items():
            print(
                f"    - {window} days: {Fore.GREEN}{weight}{Style.RESET_ALL}")
    else:
        print(f"  - Window weights: {Fore.YELLOW}Disabled{Style.RESET_ALL}")

    print(
        f"  - Max workers: {Fore.GREEN}{config.max_workers}{Style.RESET_ALL}")
    print(f"  - Stock count: {Fore.GREEN}{len(stock_list)}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}======================================{Style.RESET_ALL}")

    # Try to use ProcessPoolExecutor, fall back to ThreadPoolExecutor if needed
    try:
        executor_class = ProcessPoolExecutor
        print(
            f"{Fore.GREEN}Using ProcessPoolExecutor for concurrent data fetching{Style.RESET_ALL}")
    except Exception as e:
        print(
            f"{Fore.RED}ProcessPoolExecutor initialization failed: {e}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Falling back to ThreadPoolExecutor{Style.RESET_ALL}")
        executor_class = ThreadPoolExecutor

    # Initialize counters
    success_count = 0
    empty_count = 0
    error_count = 0
    platform_count = 0

    # List to store platform stocks
    platform_stocks = []

    cancelled = False
    error_detail = None

    # Use executor for concurrent processing
    with _ScanExecutorContext(
            executor_class, config.max_workers,
            initializer=None if use_local else baostock_login) as executor:
        # Create progress bar
        total_stocks = len(stock_list)
        pbar = tqdm(total=total_stocks, desc="Fetching stock data",
                    bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]")

        def submit(stock):
            if use_local:
                # store.db 沿用本模块的板块常量；只在本模块完成加载后再导入 reader，
                # 避免模块初始化阶段形成 platform_scanner -> store.db -> platform_scanner 的环。
                from .store.reader import load_one_kline_60m
                return executor.submit(
                    load_one_kline_60m, local_db_path, stock['code'], start_date, end_date)
            return executor.submit(fetch_kline_data, stock['code'], start_date, end_date,
                                   config.retry_attempts, config.retry_delay,
                                   frequency)

        # Process a bounded number of results as they complete. This prevents a
        # cancellation request from leaving thousands of queued Baostock calls.
        for i, (future, stock) in enumerate(_iter_bounded_futures(
                executor, stock_list, submit, should_cancel,
                max(1, config.max_workers * 2))):
            # 用户请求停止：丢掉还没开始的任务，已扫到的结果照常返回
            if should_cancel and should_cancel():
                cancelled = True
                print(f"{Fore.YELLOW}Cancel requested, stopping scan "
                      f"({i}/{total_stocks} processed){Style.RESET_ALL}")
                executor._scan_cancelled = True
                break
            stock_code = stock['code']
            stock_name = stock['name']

            try:
                # Get K-line data
                df = future.result()

                if df.empty:
                    empty_count += 1
                    pbar.set_postfix(success=success_count, empty=empty_count,
                                     error=error_count, platform=platform_count)
                    pbar.update(1)
                    continue

                if frequency == "60" and len(df) < max_window:
                    empty_count += 1
                    if update_progress:
                        update_progress(
                            scanned=i + 1, total=total_stocks,
                            found=platform_count,
                            message=f"{stock_code} 的60分钟K线不足 {max_window} 根（仅 {len(df)} 根），已跳过"
                        )
                    pbar.update(1)
                    continue

                # Analyze for platform periods
                analysis_result = analyze_stock(
                    df,
                    config.windows,
                    config.box_threshold,
                    config.ma_diff_threshold,
                    config.volatility_threshold,
                    config.volume_change_threshold,
                    config.volume_stability_threshold,
                    config.volume_increase_threshold,
                    config.use_volume_analysis,
                    config.use_breakthrough_prediction,
                    config.use_window_weights,
                    config.window_weights,
                    config.use_low_position,
                    config.high_point_lookback_days,
                    config.decline_period_days,
                    config.decline_threshold,
                    config.use_rapid_decline_detection,
                    config.rapid_decline_days,
                    config.rapid_decline_threshold,
                    config.use_breakthrough_confirmation,
                    config.breakthrough_confirmation_days,
                    config.use_box_detection,
                    config.box_quality_threshold
                )

                success_count += 1

                # If it's a platform stock, add to results
                if analysis_result["is_platform"]:
                    platform_count += 1

                    # Create result object
                    platform_stock = {
                        'code': stock_code,
                        'name': stock_name,
                        'industry': stock.get('industry', '未知行业'),
                        'platform_windows': analysis_result["platform_windows"],
                        'details': analysis_result["details"],
                        'selection_reasons': analysis_result["selection_reasons"],
                        'kline_data': df.to_dict(orient='records')
                    }

                    # Add mark lines if available
                    if "mark_lines" in analysis_result:
                        platform_stock['mark_lines'] = analysis_result["mark_lines"]
                        print(
                            f"{Fore.GREEN}添加标记线数据到股票 {stock_code}: {analysis_result['mark_lines']}{Style.RESET_ALL}")

                    # Add volume analysis results if available
                    if config.use_volume_analysis and "volume_analysis" in analysis_result:
                        platform_stock['volume_analysis'] = analysis_result["volume_analysis"]

                    # Add breakthrough prediction results if available
                    if config.use_breakthrough_prediction and "breakthrough_prediction" in analysis_result:
                        platform_stock['breakthrough_prediction'] = analysis_result["breakthrough_prediction"]

                    # Add window weight results if available
                    if config.use_window_weights and "weighted_score" in analysis_result:
                        platform_stock['weighted_score'] = analysis_result["weighted_score"]
                        platform_stock['weight_details'] = analysis_result.get(
                            "weight_details", {})

                    platform_stocks.append(platform_stock)

                    # 边扫边出：取消请求到达后不再追加新结果；当前 future
                    # 仍允许完成，但最终结果只保留停止前已经发布的命中。
                    if on_found and not (should_cancel and should_cancel()):
                        on_found(platform_stock)

                # Update progress
                if update_progress and i % 10 == 0:  # Update every 10 stocks
                    progress_pct = (i + 1) / total_stocks * 100
                    update_progress(
                        progress=int(progress_pct),
                        scanned=i + 1,
                        total=total_stocks,
                        found=platform_count,
                        message=f"已分析 {i+1}/{total_stocks} 只，发现 {platform_count} 只平台期股票"
                    )

                # 连续大量错误通常意味着数据源不可用，尽早退出而不是空转
                if error_detail and error_count >= 50 and success_count == 0:
                    print(f"{Fore.RED}Aborting scan: data source unavailable "
                          f"({error_count} consecutive errors){Style.RESET_ALL}")
                    executor._scan_cancelled = True
                    raise ConnectionError(error_detail)

            except Exception as e:
                error_count += 1
                print(
                    f"{Fore.RED}Error processing stock {stock_code}: {e}{Style.RESET_ALL}")
                import traceback
                traceback.print_exc()
                # 数据源整体不可用时（例如账号被限流），继续跑下去只会一直失败
                if error_detail is None and isinstance(e, ConnectionError):
                    error_detail = str(e)

            # Update progress bar
            pbar.set_postfix(success=success_count, empty=empty_count,
                             error=error_count, platform=platform_count)
            pbar.update(1)

        # Close progress bar
        pbar.close()
        if should_cancel and should_cancel():
            cancelled = True
            executor._scan_cancelled = True

    # Cancellation is a safe stop boundary: do not spend more time in the
    # optional fundamental/industry post-filters after the stock futures have
    # been drained. The caller merges streamed findings into the terminal
    # payload, so returning the raw hits here preserves everything found.
    if cancelled or (should_cancel and should_cancel()):
        return platform_stocks

    # 数据源整体不可用，直接抛给上层（此时已拿到部分结果也没有意义，因为几乎全是失败）
    if error_detail and success_count == 0:
        raise ConnectionError(error_detail)

    # Apply fundamental analysis filter if enabled
    if config.use_fundamental_filter:
        print(f"{Fore.CYAN}Applying fundamental analysis filter...{Style.RESET_ALL}")
        if update_progress:
            update_progress(progress=100, message=f"正在对 {platform_count} 只候选股票做基本面筛选…")
        fundamental_filtered_stocks = analyze_fundamentals(
            platform_stocks,
            use_fundamental_filter=config.use_fundamental_filter,
            revenue_growth_percentile=config.revenue_growth_percentile,
            profit_growth_percentile=config.profit_growth_percentile,
            roe_percentile=config.roe_percentile,
            liability_percentile=config.liability_percentile,
            pe_percentile=config.pe_percentile,
            pb_percentile=config.pb_percentile,
            years_to_check=config.fundamental_years_to_check
        )
        fundamental_count = len(fundamental_filtered_stocks)
        print(f"{Fore.GREEN}Fundamental analysis complete. {fundamental_count} stocks passed out of {platform_count}.{Style.RESET_ALL}")
    else:
        fundamental_filtered_stocks = platform_stocks
        fundamental_count = platform_count
        print(f"{Fore.YELLOW}Fundamental analysis filter disabled.{Style.RESET_ALL}")

    # Apply industry diversity filter
    filtered_stocks = apply_industry_diversity_filter(
        fundamental_filtered_stocks,
        expected_count=config.expected_count
    )

    # Print summary
    print(f"{Fore.CYAN}======================================{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Scan completed{Style.RESET_ALL}")
    print(f"{Fore.CYAN}======================================{Style.RESET_ALL}")
    print(
        f"Total stocks processed: {Fore.GREEN}{success_count + empty_count + error_count}{Style.RESET_ALL}")
    print(f"  - Success: {Fore.GREEN}{success_count}{Style.RESET_ALL}")
    print(f"  - Empty data: {Fore.YELLOW}{empty_count}{Style.RESET_ALL}")
    print(f"  - Errors: {Fore.RED}{error_count}{Style.RESET_ALL}")
    print(
        f"Platform stocks found: {Fore.GREEN}{platform_count}{Style.RESET_ALL}")
    if config.use_fundamental_filter:
        print(
            f"Fundamental filtered stocks: {Fore.GREEN}{fundamental_count}{Style.RESET_ALL}")
    print(
        f"Filtered stocks (industry diversity): {Fore.GREEN}{len(filtered_stocks)}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}======================================{Style.RESET_ALL}")

    # Final progress update
    if update_progress:
        update_progress(
            progress=100,
            scanned=success_count + empty_count + error_count,
            total=len(stock_list),
            found=platform_count,
            message=(
                f"已停止：共分析 {success_count + empty_count + error_count} 只，发现 {platform_count} 只平台期股票，保留 {len(filtered_stocks)} 只"
                if cancelled else
                f"扫描完成：发现 {platform_count} 只平台期股票，保留 {len(filtered_stocks)} 只"
            )
        )

    return filtered_stocks
