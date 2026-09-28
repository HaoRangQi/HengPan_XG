"""平台期扫描的数据源选择；本地模式与旧版 Baostock 模式在此分流。"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd

from .data_fetcher import (
    BaostockConnectionManager,
    fetch_industry_data,
    fetch_stock_basics,
)
from .platform_scanner import prepare_stock_list, select_markets
from .store import db as store_db
from .store.reader import latest_date as local_latest_date


@dataclass(frozen=True)
class PlatformScanSource:
    data_source: str
    stock_list: List[Dict[str, Any]]
    frequency: str
    local_db_path: Optional[str] = None
    end_date: Optional[str] = None


def _local_source(markets, frequency, use_fundamental_filter, db_path):
    if frequency != "60":
        raise ValueError("本地行情库目前只支持 60 分钟 K 线")
    if use_fundamental_filter:
        raise ValueError("本地行情库不含财务指标；请关闭基本面筛选，或改用旧版联网扫描")

    boards = list(markets or store_db.KLINE_BOARDS)
    unsupported = sorted(set(boards) - set(store_db.KLINE_BOARDS))
    if unsupported:
        raise ValueError(f"本地行情库不支持这些板块：{', '.join(unsupported)}")

    path = db_path or store_db.DB_PATH
    try:
        with store_db.open_readonly_db(path) as conn:
            stocks = store_db.stock_list_with_kline(conn, "60", boards)
            end_date = local_latest_date(
                conn, boards, [stock["code"] for stock in stocks])
    except Exception as exc:
        raise ValueError("无法读取本地行情库，请先到「数据管理」同步本地数据") from exc

    if not stocks or not end_date:
        raise ValueError("所选板块没有可扫描的本地 60 分钟行情，请先到「数据管理」同步")
    return PlatformScanSource("local", stocks, "60", path, end_date)


def _baostock_source(markets, frequency):
    with BaostockConnectionManager():
        stock_basics = fetch_stock_basics()
        try:
            industries = fetch_industry_data()
        except Exception:
            industries = pd.DataFrame()
    stocks = select_markets(prepare_stock_list(stock_basics, industries), markets)
    if not stocks:
        raise ValueError("所选板块没有匹配的股票，请检查板块设置")
    return PlatformScanSource("baostock", stocks, frequency)


def prepare_platform_scan_source(data_source, markets, frequency,
                                 use_fundamental_filter=False, db_path=None):
    """准备扫描股票池与 K 线来源；本地模式不会触发任何联网函数。"""
    if data_source == "local":
        return _local_source(markets, frequency, use_fundamental_filter, db_path)
    if data_source == "baostock":
        return _baostock_source(markets, frequency)
    raise ValueError("data_source must be 'local' or 'baostock'")
