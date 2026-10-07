"""
横盘-U 扫描：把末端锚定横盘箱体算法用到 crypto.db 的 1 小时线上。

判定算法完全共用 api/hengpan/anchored_box.py 和 tolerant_box.py，和横盘-A 一个口径。
差别只在数据源和几个字段：交易对代替股票代码、类别代替板块、成交额是 USDT、
没有换手率（换成回验区间的平均成交笔数）。

加密 7×24 交易，没有停牌，回验窗口里缺 K 线只能是本地还没同步全。
这种窗口会把断档前后压成一段看似连续的走势，和 A 股的停牌缺口一样不能当箱体看。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional

import pandas as pd

from ..data_quality import matches_scan_anchor

from ..hengpan.anchored_box import BOUNDARY_BAND, BOX_TYPE, _mean, extract_series
from ..hengpan.scanner import ADAPTIVE_MODES, evaluate_rule
from ..hengpan import ma_flat
from . import db
from .reader import load_kline

INTERVAL = "1h"
INTERVAL_MS = db.INTERVALS[INTERVAL]
# 卡片和大图用到的 K 线字段；amount 由 quote_asset_volume 映射而来（单位 USDT）
KLINE_COLUMNS = ["date", "open", "high", "low", "close", "volume", "amount"]
# 从库里取的原始列，比全表窄一截，几百个交易对一次读完也不占多少内存
SOURCE_COLUMNS = ["open", "high", "low", "close", "volume", "quote_asset_volume",
                  "number_of_trades"]
# 一次从库里读多少个交易对
SYMBOL_BATCH = 60


def beijing_day_end_ms(scan_date: str) -> int:
    """北京时间某一天的最后一毫秒，对应库里的 UTC 毫秒。"""
    return int(pd.Timestamp(f"{scan_date} 23:59:59.999", tz="Asia/Shanghai").value // 1_000_000)


def latest_scan_date(conn, categories: Iterable[str]) -> Optional[str]:
    """本地最新一根 1 小时线所属的北京时间日期；一根都没有时返回 None。"""
    times = []
    for category in categories:
        row = conn.execute(
            f'SELECT MAX("open_time") FROM {db.kline_table(INTERVAL, category)}').fetchone()
        if row and row[0]:
            times.append(int(row[0]))
    if not times:
        return None
    return pd.Timestamp(max(times), unit="ms", tz="UTC").tz_convert("Asia/Shanghai").strftime("%Y-%m-%d")


def has_kline_on(conn, scan_date: str, categories: Iterable[str]) -> bool:
    """所选类别在这一天有没有 1 小时线。"""
    start = beijing_day_end_ms(scan_date) - 86_399_999
    end = beijing_day_end_ms(scan_date)
    for category in categories:
        row = conn.execute(
            f'SELECT 1 FROM {db.kline_table(INTERVAL, category)} '
            'WHERE "open_time" BETWEEN ? AND ? LIMIT 1', (start, end)).fetchone()
        if row:
            return True
    return False


def fetch_range(scan_date: str, max_lookback: int) -> tuple:
    """
    取数窗口：扫描日末尾往前若干根 1 小时线。

    扫描日当天不一定走完（最新一根可能是上午那几个小时），窗口要比回验根数宽出至少一天，
    否则末端往前数不满 lookback + 1 根。再按回验根数留一倍余量，图上能看到箱体之前的走势，
    和横盘-A 的取数口径一致；多读的部分不参与判定。
    """
    end_ms = beijing_day_end_ms(scan_date)
    bars = max_lookback * 2 + 48
    return end_ms - bars * INTERVAL_MS, end_ms


def new_stats(scan_date: Optional[str], rules: List[Dict]) -> Dict[str, Any]:
    """
    扫描统计。跳过原因是全局的（一个交易对对所有规则一起跳过），入选情况按规则分别统计。
    结构与横盘-A 相同，只把「窗口内停牌」换成「窗口内缺 K 线」。
    """
    return {
        "scan_date": scan_date,
        # stale 扫描日没有 K 线（已下架、未上架或还没同步）/ insufficient K 线不足 /
        # failed 读取失败 / gap 每组规则的回验窗口里都缺 K 线
        "skipped": {"stale": 0, "insufficient": 0, "failed": 0, "gap": 0},
        "truncated": 0,
        "rules": {rule["id"]: {
            "analyzed": 0,
            "passed_full": 0,
            "passed_body": 0,
            "near": 0,
            "rescued": 0,
            "gap": 0,
            "over_amplitude": 0,
        } for rule in rules},
    }


def window_has_gap(open_times, lookback: int, anchored: bool = True) -> bool:
    """
    回验窗口（末端 + 之前 lookback 根）里是否缺 K 线。

    1 小时线本该根根等距，首尾时间差等于 (根数 - 1) × 一小时就是连续的。
    """
    required = lookback + 1 if anchored else lookback
    if open_times is None or len(open_times) < required:
        return False
    window = open_times[len(open_times) - required:]
    return int(window[-1]) - int(window[0]) != (required - 1) * INTERVAL_MS


def lookback_window(box_type: str, lookback: int, total: int) -> slice:
    """回验区间切片，和 anchored_box / tolerant_box 内部取的窗口一致。"""
    if box_type == "tolerant":
        return slice(total - lookback, total)
    return slice(total - lookback - 1, total - 1)


def build_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """把 reader 的输出整理成判定算法需要的列：amount 用 USDT 成交额。"""
    if raw.empty:
        return raw
    frame = raw.copy()
    frame["amount"] = frame["quote_asset_volume"]
    return frame.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


def load_frames(conn, symbols: List[Dict], start_ms: int, end_ms: int) -> Dict[str, pd.DataFrame]:
    """按类别批量读取一批交易对的 K 线，返回 symbol -> 已整理的 DataFrame。"""
    frames: Dict[str, pd.DataFrame] = {}
    by_category: Dict[str, List[str]] = {}
    for item in symbols:
        by_category.setdefault(item["category"], []).append(item["symbol"])
    for category, names in by_category.items():
        raw = load_kline(conn, INTERVAL, [category], names, start_ms=start_ms, end_ms=end_ms,
                         columns=SOURCE_COLUMNS)
        if raw.empty:
            continue
        for symbol, group in build_frame(raw).groupby("symbol", sort=False):
            frames[symbol] = group.reset_index(drop=True)
    return frames


def build_item(symbol_info: Dict, frame: pd.DataFrame, matches: Dict) -> Dict[str, Any]:
    """把一个命中的交易对整理成接口返回的结构。上轨下轨按规则各不相同，都放在 matches 里。"""
    kline = frame[[column for column in KLINE_COLUMNS if column in frame]]
    last = frame.iloc[-1]
    return {
        "symbol": symbol_info["symbol"],
        "base_asset": symbol_info.get("baseAsset") or symbol_info["symbol"],
        "category": symbol_info["category"],
        "category_label": db.CATEGORY_LABELS[symbol_info["category"]],
        "quote_volume": symbol_info.get("quoteVolume") or 0.0,
        "last_price": symbol_info.get("lastPrice"),
        "price_change_percent": symbol_info.get("priceChangePercent"),
        "date": str(last["date"]),
        "close": float(last["close"]),
        "amplitude": float((last["high"] - last["low"]) / last["close"]),
        "matches": matches,
        "kline_data": kline.astype(object).where(kline.notna(), None).to_dict(orient="records"),
    }


def analyze_symbol(symbol_info: Dict, frame: pd.DataFrame, rules: List[Dict],
                   scan_date: str, stats: Dict) -> Optional[Dict[str, Any]]:
    """
    单个交易对：跳过扫描日没有 K 线和数据不足的，其余按每组规则各算一遍。
    只要有一组规则实体口径通过就返回结果条目，命中的规则都记在 matches 里。
    """
    use_ma = any(rule["params"].get("box_type") in ADAPTIVE_MODES for rule in rules)
    frame = ma_flat.closed_frame(frame, INTERVAL)
    if not matches_scan_anchor(frame, scan_date):
        stats["skipped"]["stale"] += 1
        return None

    series = extract_series(frame)
    continuous = ma_flat.continuous_frame(frame, INTERVAL)
    ma_frame = continuous if use_ma else None
    ma_series = extract_series(ma_frame) if use_ma else None
    open_times = frame["open_time"].to_numpy()
    trades = frame["number_of_trades"].to_numpy(dtype=float) \
        if "number_of_trades" in frame else None
    total = len(frame)
    matches = {}
    analyzed = gapped = False
    for rule in rules:
        box_type = rule["params"].get("box_type", BOX_TYPE)
        lookback = rule["params"]["lookback"]
        has_gap = (ma_frame.attrs.get("continuity_gap", False) and
                   len(ma_frame) < ADAPTIVE_MODES[rule["params"]["box_type"]].required_bars(rule["params"])) if box_type in ADAPTIVE_MODES else \
            (continuous.attrs.get("continuity_gap", False) and
             len(continuous) < lookback + (box_type != "tolerant") and
             len(frame) >= lookback + (box_type != "tolerant"))
        if has_gap:
            stats["rules"][rule["id"]]["gap"] += 1
            gapped = True
            continue
        box = evaluate_rule(ma_series if box_type in ADAPTIVE_MODES else series, rule["params"])
        if box is None:  # 有效 K 线不够这组规则回验，换下一组
            continue
        analyzed = True
        counter = stats["rules"][rule["id"]]
        counter["analyzed"] += 1
        # 十字星分界只存在于固定箱高模式，振幅模式不区分十字星
        if box_type == "fixed" and \
                abs(box["amplitude"] - rule["params"]["doji_amplitude"]) <= BOUNDARY_BAND:
            counter["near"] += 1
            other = "normal" if box["mode"] == "doji" else "doji"
            if not box["passed_full"] and evaluate_rule(series, rule["params"], mode=other)["passed_full"]:
                counter["rescued"] += 1
        counter["over_amplitude"] += bool(box.get("over_amplitude"))
        counter["passed_full"] += box["passed_full"]
        counter["passed_body"] += box["passed_body"]
        if box["passed_body"]:
            # 加密没有换手率，用回验区间的平均成交笔数衡量活跃度
            window = slice(total - (box["box_bars"] if box_type == "boll_box" else box["flat_bars"]), total) if box_type in ADAPTIVE_MODES else \
                lookback_window(box_type, lookback, total)
            box["avg_trades"] = _mean(trades[window]) if trades is not None else None
            matches[rule["id"]] = box

    if not analyzed:
        # 没有一组规则能判定：只要有一组是因为缺 K 线，就记缺口，否则记数据不足
        stats["skipped"]["gap" if gapped else "insufficient"] += 1
        return None
    return build_item(symbol_info, frame, matches) if matches else None


def scan_hengpan(conn, symbols: List[Dict], rules: List[Dict], scan_date: str, stats: Dict,
                 update_progress: Optional[Callable] = None,
                 should_cancel: Optional[Callable] = None,
                 on_found: Optional[Callable] = None) -> List[Dict[str, Any]]:
    """
    逐个扫描币池，返回至少命中一组规则的交易对（按交易对名排序）。

    读的是本地 SQLite，没有网络等待，按批顺序读取即可，不需要横盘-A 那样的进程池。
    """
    max_lookback = max(rule["params"]["lookback"] for rule in rules)
    start_ms, end_ms = fetch_range(scan_date, max_lookback)
    if any(rule["params"].get("box_type") in ADAPTIVE_MODES for rule in rules):
        start_ms = None  # 均线走平读取全部已存历史，实际长度由算法决定。
    latest = latest_scan_timestamp(conn, symbols, scan_date)
    scan_anchor = latest if latest and latest[:10] == scan_date else scan_date
    total = len(symbols)
    found: List[Dict[str, Any]] = []
    scanned = 0
    cancelled = False

    for offset in range(0, total, SYMBOL_BATCH):
        if should_cancel and should_cancel():
            cancelled = True
            break
        batch = symbols[offset:offset + SYMBOL_BATCH]
        try:
            frames = load_frames(conn, batch, start_ms, end_ms)
        except Exception as error:
            stats["skipped"]["failed"] += len(batch)
            raise ConnectionError(f"读取本地加密行情失败：{error}")
        for symbol_info in batch:
            if should_cancel and should_cancel():
                cancelled = True
                break
            scanned += 1
            frame = frames.get(symbol_info["symbol"])
            if frame is None or frame.empty:
                stats["skipped"]["stale"] += 1
            else:
                item = analyze_symbol(symbol_info, frame, rules, scan_anchor, stats)
                if item:
                    if on_found:
                        retained = on_found(item)
                        if isinstance(retained, dict):
                            item = retained
                    found.append(item)
        if update_progress:
            update_progress(scanned=scanned, total=total, found=len(found),
                            message=f"已分析 {scanned}/{total} 个交易对，找到 {len(found)} 个横盘箱体")
        if cancelled:
            break

    found.sort(key=lambda item: item["symbol"])  # 前端会按当前规则重新排序，这里只求顺序稳定
    if update_progress:
        summary = "、".join(f"{rule['id']} 组 {stats['rules'][rule['id']]['passed_full']} 个"
                           for rule in rules)
        update_progress(scanned=scanned, total=total, found=len(found),
                        message=f"{'已停止' if cancelled else '扫描完成'}：分析 {scanned} 个，"
                                f"命中 {len(found) + stats['truncated']} 个，整体口径入选 {summary}")
    return found


def latest_scan_timestamp(conn, symbols, scan_date=None, now=None):
    """Latest closed bar in exactly the selected symbol universe (Beijing text)."""
    current = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")
    if current.tzinfo is None:
        current = current.tz_localize("Asia/Shanghai")
    end_ms = int(current.value // 1_000_000) - INTERVAL_MS
    if scan_date:
        end_ms = min(end_ms, beijing_day_end_ms(scan_date))
    times = []
    for category in dict.fromkeys(item["category"] for item in symbols):
        selected = [item["symbol"] for item in symbols if item["category"] == category]
        placeholders = ",".join("?" * len(selected))
        row = conn.execute(f'SELECT MAX("open_time") FROM {db.kline_table(INTERVAL, category)} '
                           f'WHERE "symbol" IN ({placeholders}) AND "open_time" <= ?',
                           [*selected, end_ms]).fetchone()
        if row and row[0] is not None:
            times.append(int(row[0]))
    return (pd.Timestamp(max(times), unit="ms", tz="UTC").tz_convert("Asia/Shanghai")
            .strftime("%Y-%m-%d %H:%M:%S")) if times else None
