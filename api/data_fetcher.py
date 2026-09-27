"""
Data Fetcher module for retrieving stock data from Baostock.
Implements robust connection handling and retry logic.
"""
import baostock as bs
import pandas as pd
import time
import threading
from typing import List, Dict, Any, Optional
from colorama import Fore, Style
import traceback

# 必须在使用 baostock 之前导入：修掉它收包循环里连接断开就空转的死循环
from . import baostock_patch  # noqa: F401

# Thread-local storage for Baostock connections
_thread_local = threading.local()

# 登出最多等这么久（秒）。baostock 的 send_msg 里是 `while True: recv()`，
# 连接已断时 recv 立刻返回空字节却永远等不到结束标记，会一直空转吃满 CPU。
# 登出只是通知服务端，超时放弃不影响后续使用，所以宁可丢弃也不能卡住调用方。
LOGOUT_TIMEOUT = 5


class BaostockBlacklisted(ConnectionError):
    """Baostock 把本机 IP 列入黑名单（错误码 10001011）。重试只会加重封禁，必须整轮中止。"""


def is_blacklist_error(message: str) -> bool:
    return "黑名单" in str(message) or "10001011" in str(message)


def baostock_login() -> None:
    """
    Login to Baostock API with thread-local connection.
    Each thread/process will have its own connection.
    """
    # Check if already logged in
    if hasattr(_thread_local, 'logged_in') and _thread_local.logged_in:
        return
    
    # Login
    lg = bs.login()
    if lg.error_code != '0':
        print(f"{Fore.RED}Baostock login failed: {lg.error_msg}{Style.RESET_ALL}")
        if is_blacklist_error(lg.error_msg):
            raise BaostockBlacklisted(f"Baostock 拒绝登录：{lg.error_msg}")
        raise ConnectionError(f"Baostock login failed: {lg.error_msg}")
    
    _thread_local.logged_in = True
    print(f"{Fore.GREEN}Baostock login successful in thread {threading.current_thread().name}{Style.RESET_ALL}")

def baostock_logout() -> None:
    """
    Logout from Baostock API and clean up thread-local connection.

    连接已断时 baostock 的 logout 会永久卡住（见 LOGOUT_TIMEOUT），所以放到守护线程里
    执行并限时等待：超时就放弃登出，让调用方继续往下走。
    """
    if not (hasattr(_thread_local, 'logged_in') and _thread_local.logged_in):
        return

    # 先清标记：无论登出成功与否，这个连接都不该再被复用
    _thread_local.logged_in = False
    thread_name = threading.current_thread().name
    worker = threading.Thread(target=bs.logout, name=f"baostock-logout-{thread_name}", daemon=True)
    worker.start()
    worker.join(LOGOUT_TIMEOUT)
    if worker.is_alive():
        print(f"{Fore.YELLOW}Baostock logout timed out after {LOGOUT_TIMEOUT}s in thread {thread_name}, "
              f"abandoning the dead connection{Style.RESET_ALL}")
    else:
        print(f"{Fore.GREEN}Baostock logout successful in thread {thread_name}{Style.RESET_ALL}")

def baostock_relogin() -> None:
    """
    Re-login to Baostock API (logout first, then login again).
    """
    baostock_logout()
    baostock_login()

class BaostockConnectionManager:
    """
    Context manager for Baostock connections.
    Ensures proper login/logout handling.
    """
    def __enter__(self):
        baostock_login()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        baostock_logout()
        return False  # Don't suppress exceptions

def _fetch_metadata_with_retry(label: str, query_fn,
                               retry_attempts: int = 3,
                               retry_delay: int = 1,
                               allow_empty: bool = False) -> pd.DataFrame:
    """
    Run a whole-market metadata query, retrying with a fresh login.

    A dropped connection leaves the server answering '用户未登录' on the next
    query. Without a retry that single blip aborts the entire scan before it
    starts, so mirror the retry/re-login loop fetch_kline_data already uses.

    Args:
        label: Human-readable name used in log messages and errors
        query_fn: Zero-arg callable issuing the Baostock query
        retry_attempts: Maximum number of attempts
        retry_delay: Base delay between attempts in seconds
        allow_empty: Treat an empty result as success instead of retrying.
            按日期取复权因子这类查询，当天没有除权就是空的，属于正常结果。

    Returns:
        pd.DataFrame: Query result

    Raises:
        ConnectionError: If every attempt fails
    """
    last_error = ""

    for attempt in range(1, retry_attempts + 1):
        try:
            baostock_login()
            rs = query_fn()

            if rs.error_code == '0':
                rows = []
                while rs.next():
                    rows.append(rs.get_row_data())

                if rows or allow_empty:
                    return pd.DataFrame(rows, columns=rs.fields)
                last_error = "no rows returned"
            else:
                last_error = rs.error_msg

        except BaostockBlacklisted:
            raise            # 黑名单：重试只会加重封禁，直接上抛
        except Exception as e:
            last_error = str(e)

        if is_blacklist_error(last_error):
            raise BaostockBlacklisted(f"{label} query failed: {last_error}")

        print(f"{Fore.YELLOW}Attempt {attempt}/{retry_attempts}: {label} query failed: "
              f"{last_error}{Style.RESET_ALL}")

        if attempt < retry_attempts:
            time.sleep(retry_delay * (1 + attempt * 0.5))
            baostock_relogin()

    raise ConnectionError(
        f"Failed to query {label} after {retry_attempts} attempts: {last_error}")


def fetch_stock_basics() -> pd.DataFrame:
    """
    Fetch basic information for all stocks.

    Returns:
        pd.DataFrame: DataFrame containing stock basic information

    Raises:
        ConnectionError: If Baostock connection fails
    """
    with BaostockConnectionManager():
        print(f"{Fore.CYAN}Fetching stock basic information...{Style.RESET_ALL}")
        return _fetch_metadata_with_retry("stock basics", bs.query_stock_basic)

def fetch_industry_data() -> pd.DataFrame:
    """
    Fetch industry classification data for all stocks.

    Returns:
        pd.DataFrame: DataFrame containing industry classification

    Raises:
        ConnectionError: If Baostock connection fails
    """
    with BaostockConnectionManager():
        print(f"{Fore.CYAN}Fetching industry classification data...{Style.RESET_ALL}")
        return _fetch_metadata_with_retry("industry data", bs.query_stock_industry)

def fetch_kline_data(code: str, start_date: str, end_date: str,
                     retry_attempts: int = 3,
                     retry_delay: int = 1,
                     frequency: str = "d") -> pd.DataFrame:
    """
    Fetch K-line data for a specific stock with retry logic.
    
    Args:
        code: Stock code (e.g., 'sh.600000')
        start_date: Start date in 'YYYY-MM-DD' format
        end_date: End date in 'YYYY-MM-DD' format
        retry_attempts: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds
    
    Returns:
        pd.DataFrame: DataFrame containing K-line data
    """
    if frequency not in ("d", "60"):
        raise ValueError("frequency must be 'd' or '60'")
    retries = 0
    
    while True:
        try:
            # Ensure we're logged in
            baostock_login()
            
            # Query historical K-line data
            fields = ("date,time,code,open,high,low,close,volume,amount,adjustflag"
                      if frequency == "60" else
                      "date,open,high,low,close,volume,turn,preclose,pctChg,peTTM,pbMRQ")
            rs = bs.query_history_k_data_plus(
                code,
                fields,
                start_date=start_date,
                end_date=end_date,
                frequency=frequency,
                adjustflag="2"     # Forward adjusted prices
            )
            
            # Check for API errors
            if rs.error_code != '0':
                retries += 1
                print(f"{Fore.YELLOW}Attempt {retries}/{retry_attempts}: Baostock query failed for {code}. Error: {rs.error_msg}{Style.RESET_ALL}")
                
                if retries >= retry_attempts:
                    print(f"{Fore.RED}Failed to fetch data for {code} after {retry_attempts} attempts{Style.RESET_ALL}")
                    return pd.DataFrame()
                
                # Retry with re-login
                time.sleep(retry_delay * (1 + retries * 0.5))
                baostock_relogin()
                continue
            
            # Process the data if query was successful
            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())
            
            # Convert to DataFrame
            if not data_list:
                print(f"{Fore.YELLOW}No data returned for {code} from {start_date} to {end_date}{Style.RESET_ALL}")
                return pd.DataFrame()
            
            df = pd.DataFrame(data_list, columns=rs.fields)
            
            # Convert numeric columns
            numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'turn', 'preclose', 'pctChg', 'peTTM', 'pbMRQ', 'amount', 'adjustflag']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            return df
            
        except Exception as e:
            retries += 1
            print(f"{Fore.RED}Attempt {retries}/{retry_attempts}: Exception while fetching data for {code}: {e}{Style.RESET_ALL}")
            
            if retries >= retry_attempts:
                print(f"{Fore.RED}Failed to fetch data for {code} after {retry_attempts} attempts{Style.RESET_ALL}")
                return pd.DataFrame()
            
            # Retry with re-login
            time.sleep(retry_delay * (1 + retries * 0.5))
            baostock_relogin()
