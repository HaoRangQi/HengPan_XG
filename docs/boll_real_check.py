"""
横盘思路 5（布林轨道箱体法）的真实数据验证脚本。

数据源：本地 market.db 的 60m 线（kline_60m_{sh_main,sz_main,sz_gem}）。
只读数据库，不联网、不写文件。配套文档：横盘思路5-布林轨道箱体法.md

两个分析窗口（原样保留，两组实验的时间段不同）：
  W120 —— 每只票最后 120 根，用于形态对照类实验（§4.5 / §4.7 / §4.8 / §4.3 真实数据表）
  W176 —— 每只票最后 176 根，前 120 训练 + 后 56 样本外（§3.2 / §3.3 / §五 / §七）

打乱对照：对数收益随机置换后累加，高低价相对实体中点的偏移跟随同一置换 ——
保留波动率分布与每根振幅结构，只破坏时序结构。真实减打乱才是净优势。

用法：api/.venv/bin/python docs/boll_real_check.py
"""
import itertools
import sqlite3

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

DB = "api/data/market.db"
TABLES = ("kline_60m_sh_main", "kline_60m_sz_main", "kline_60m_sz_gem")
N120 = 120              # 形态对照窗口
TRAIN, OOS = 120, 56    # 训练窗 / 样本外窗
BN, BK = 20, 2.0        # 布林默认周期与倍数
L_MIN, L_MAX = 30, 120  # 箱体长度搜索范围
SEED = 42

# §六 参数表的推荐值
TH_DRIFT, TH_TIGHT, TH_BW = 3.0, 0.6, 8.0
# 思路 4 判据 A/B/C/D 的原阈值（为日线 N=80 标定）
TH_A, TH_B, TH_C = 2.0, 4.5, 0.6


# ============================================================ 取数

def load():
    """读全市场 60m 线，返回 {code: (o,h,l,c,v)}，每只最多保留 TRAIN+OOS 根。"""
    conn = sqlite3.connect(DB)
    ok = set(pd.read_sql("select code from stock_basic where status='1' and type='1'",
                         conn)["code"])
    frames = []
    for table in TABLES:
        part = pd.read_sql(f"select date, time, code, open, high, low, close, volume "
                           f"from {table} order by code, date, time", conn)
        part["volume"] = pd.to_numeric(part["volume"], errors="coerce")   # 库里是 TEXT
        frames.append(part)
    div = pd.read_sql("select code, dividOperateDate from adjust_factor", conn)
    conn.close()

    df = pd.concat(frames, ignore_index=True)
    df = df[df["code"].isin(ok)]
    # 窗口期内除权：本地存的是不复权价，会有跳空，剔除
    recent = set(div.loc[div["dividOperateDate"] >= df["date"].min(), "code"])

    out = {}
    for code, group in df.groupby("code", sort=False):
        if code in recent or len(group) < N120:
            continue
        group = group.tail(TRAIN + OOS)
        cols = [group[k].to_numpy(dtype=float)
                for k in ("open", "high", "low", "close", "volume")]
        if not np.isfinite(cols[:4]).all() or (cols[2] <= 0).any():
            continue
        out[code] = tuple(cols)
    return out


# ============================================================ 基础量

def bands(x, n=BN, k=BK):
    """滚动布林带。返回 (中轨, 标准差, 上轨, 下轨)，均短 n-1 个点。"""
    window = sliding_window_view(x, n)
    mid, std = window.mean(axis=1), window.std(axis=1)   # ddof=0，与 TA-Lib 一致
    return mid, std, mid + k * std, mid - k * std


def ols(y):
    """最小二乘斜率。"""
    t = np.arange(len(y), dtype=float) - (len(y) - 1) / 2
    return float(np.dot(t, y - y.mean()) / np.dot(t, t))


def theil_sen(y):
    """Theil-Sen 稳健斜率（全枚举点对中位数），与思路 4 判据 A 同口径。"""
    i, j = np.triu_indices(len(y), k=1)
    return float(np.median((y[j] - y[i]) / (j - i)))


def box_of(x):
    """静态水平箱体（布林周期 = 箱体长度的退化形态）。返回 (漂移%, 标准差)。"""
    return ols(x) * len(x) * 100, float(x.std())


def shuffle_series(x, high, low, generator):
    """打乱对照：收益随机置换，高低价偏移跟随同一置换。"""
    diff = np.diff(x)
    order = generator.permutation(len(diff))
    shuffled = x[0] + np.concatenate(([0.0], np.cumsum(diff[order])))
    perm = np.concatenate(([0], order + 1))
    return shuffled, shuffled + (high - x)[perm], shuffled + (low - x)[perm]


def banner(text):
    print(f"\n{'=' * 100}\n{text}\n{'=' * 100}")


def pct(values, q):
    return float(np.percentile(values, q)) if len(values) else float("nan")


# ============================================================ 数据装载

print("读取本地 60m 线 ...")
DATA = load()
# W120：最后 120 根，形态对照用
C120 = [c for c, v in DATA.items() if len(v[3]) >= N120]
X120 = {c: np.log((DATA[c][0][-N120:] + DATA[c][3][-N120:]) / 2) for c in C120}
# W176：176 根齐全的，训练 + 样本外用
C176 = [c for c, v in DATA.items() if len(v[3]) >= TRAIN + OOS]
X = {c: np.log((DATA[c][0] + DATA[c][3]) / 2) for c in C176}
H = {c: np.log(DATA[c][1]) for c in C176}
LO = {c: np.log(DATA[c][2]) for c in C176}
print(f"W120（最后 {N120} 根）：{len(C120)} 只")
print(f"W176（训练 {TRAIN} + 样本外 {OOS}）：{len(C176)} 只")

_rng = np.random.default_rng(SEED)
SH, SH_H, SH_L = {}, {}, {}
for c in C176:
    SH[c], SH_H[c], SH_L[c] = shuffle_series(X[c], H[c], LO[c], _rng)
SIG1 = float(np.median([np.diff(X[c][:TRAIN]).std() for c in C176]))
RW = {c: np.cumsum(_rng.normal(0, SIG1, TRAIN + OOS)) for c in C176}


# ============================================================ §4.8 贴合度

def exp_edges_vs_real():
    banner("§4.8  布林上下轨 vs 实际箱体边界（W120，正 = 轨在实际边界之外，%）")
    up_dev, lo_dev = [], []
    for c in C120:
        x = X120[c]
        _, _, up, lo = bands(x)
        seg_h = float(DATA[c][1][-BN:].max())
        seg_l = float(DATA[c][2][-BN:].min())
        up_dev.append((np.exp(up[-1]) - seg_h) / seg_h * 100)
        lo_dev.append((np.exp(lo[-1]) - seg_l) / seg_l * 100)
    up_dev, lo_dev = np.array(up_dev), np.array(lo_dev)
    total = up_dev - lo_dev
    print(f"{'分位':<8}{'上轨偏离实际最高':>18}{'下轨偏离实际最低':>18}{'两侧偏离之和':>16}")
    for q in (5, 25, 50, 75, 95):
        print(f"{'P' + str(q):<8}{pct(up_dev, q):>18.2f}{pct(lo_dev, q):>18.2f}"
              f"{pct(total, q):>16.2f}")
    print(f"\n  中位：布林箱体比实际箱体窄 {-pct(total, 50):.2f} 个百分点 —— 视觉上「完全等同」不是错觉")

    print(f"\n  为什么贴合：正态下 n 个样本极差期望 = d2(n)·σ，而 ±2σ 宽度恒为 4σ")
    d2 = {10: 3.078, 15: 3.472, 20: 3.735, 30: 4.086, 40: 4.322, 60: 4.639}
    print(f"\n{'n':>5}{'d2(n)':>10}{'理论 4σ/极差':>16}{'实测 布林宽/实际极差':>22}")
    for n in (10, 15, 20, 30, 40, 60):
        ratios = []
        for c in C120:
            x = X120[c]
            w = sliding_window_view(x, n)[-1]
            span = np.log(DATA[c][1][-n:].max()) - np.log(DATA[c][2][-n:].min())
            if span > 0:
                ratios.append(4 * w.std() / span)
        tag = "  ← 甜蜜点" if n == 20 else ""
        print(f"{n:>5}{d2[n]:>10.3f}{4 / d2[n]:>16.3f}{np.median(ratios):>22.3f}{tag}")
    print("\n  d2(20)=3.735≈4 —— 默认参数恰好落在「4σ = 样本极差」处，是数值巧合而非识别能力")


# ============================================================ §4.5 局部 vs 全局

def exp_local_vs_global():
    banner("§4.5  布林末端箱体（局部 n 根）vs 全窗口箱体（120 根）")
    real = np.median([(np.log(DATA[c][1][-N120:].max())
                       - np.log(DATA[c][2][-N120:].min())) * 100 for c in C120])
    print(f"{'布林周期 n':>12}{'布林带宽中位 %':>18}{'全窗口实际箱体中位 %':>22}{'低估倍数':>12}")
    for n in (20, 40, 60):
        bw = np.median([2 * BK * sliding_window_view(X120[c], n)[-1].std() * 100 for c in C120])
        print(f"{n:>12}{bw:>18.2f}{real:>22.2f}{real / max(bw, 1e-9):>12.2f}x")
    print("\n  末端矩形只描述最近 n 根，左边那 100 根它不管 —— 横盘要求全窗口箱体")


# ============================================================ §4.7 带内比例

def exp_inside_ratio():
    banner("§4.7  「价格被上下轨包住」有信息量吗（W120）")
    rows = {}
    for c in C120:
        x = X120[c]
        mid, std, up, lo = bands(x)
        xs = x[BN - 1:]
        drift = theil_sen(x) * len(x) * 100
        rows[c] = (float(np.mean((xs <= up) & (xs >= lo))) * 100,
                   (np.log(DATA[c][1][-N120:].max())
                    - np.log(DATA[c][2][-N120:].min())) * 100,
                   abs(drift),
                   abs(ols(up) * len(mid) * 100) < TH_A
                   and abs(ols(lo) * len(mid) * 100) < TH_A
                   and abs(theil_sen(std) * len(mid) / max(np.median(std), 1e-12)) < 0.30)
    inside = np.array([rows[c][0] for c in C120])
    rng_ = np.array([rows[c][1] for c in C120])
    drift = np.array([rows[c][2] for c in C120])
    rect = np.array([rows[c][3] for c in C120])
    print(f"{'分组':<26}{'只数':>8}{'收盘在带内比例 %':>18}{'实际箱体幅度中位 %':>20}")
    for label, mask in (("全市场", np.ones(len(C120), bool)),
                        ("布林判长方形", rect),
                        ("明显趋势 漂移>10%", drift > 10),
                        ("巨震 实际幅度>25%", rng_ > 25)):
        if mask.sum():
            print(f"{label:<26}{mask.sum():>8}{inside[mask].mean():>18.2f}"
                  f"{np.median(rng_[mask]):>20.2f}")
    print(f"\n  各组均在 {inside.mean():.1f}% 附近 —— ±2σ 的定义保证了这件事，零信息量")
    if rect.sum():
        print(f"  布林判长方形的 {rect.sum()} 只里，实际箱体 >15% 的占 "
              f"{np.mean(rng_[rect] > 15) * 100:.1f}%、>25% 的占 {np.mean(rng_[rect] > 25) * 100:.1f}%")


# ============================================================ §4.3 公平对照

def exp_fair_compare():
    banner("§4.3  公平对照：阈值按百分位秩标定，入选数量对齐（W120）")
    cols = []
    for c in C120:
        x = X120[c]
        mid, std, up, lo = bands(x)
        L = len(mid)
        tilt = abs(ols(mid)) * L * 100
        flare = abs(theil_sen(std)) * L / max(float(np.median(std)), 1e-12)
        bw = float((2 * BK * std).mean()) * 100
        beta = theil_sen(x)
        drift = abs(beta * len(x)) * 100
        r = x - beta * np.arange(len(x))
        q05, q95 = np.quantile(r, 0.05), np.quantile(r, 0.95)
        band = (q95 - q05) * 100
        d1 = np.diff(x).var()
        vr = max((x[k:] - x[:-k]).var() / (k * d1) for k in (10, 20, 40)) if d1 > 0 else 9.9
        breakout = max(r[-1] - q95, q05 - r[-1]) / max(q95 - q05, 1e-9)
        real = (np.log(DATA[c][1][-N120:].max()) - np.log(DATA[c][2][-N120:].min())) * 100
        cols.append((tilt, flare, bw, drift, band, vr, breakout, real))
    A = np.array(cols)
    tilt, flare, bw, drift, band, vr, breakout, real = A.T

    def rank(*series):
        """各维度取百分位秩后求最大值 —— 等价于同时收紧所有阈值。"""
        return np.max([np.argsort(np.argsort(s)) / len(s) for s in series], axis=0)

    schemes = {"布林原判据（倾斜+喇叭）": rank(tilt, flare),
               "布林+带宽水平": rank(tilt, flare, bw),
               "布林去喇叭（倾斜+带宽）": rank(tilt, bw),
               "已有 A/B/C/D": rank(drift, band, vr, breakout),
               "已有 A+B（漂移+带宽）": rank(drift, band)}
    tops = (50, 100, 200, 400)
    print("  入选票的全窗口实际箱体幅度中位数 —— 越小判别力越强\n")
    print(f"{'方案':<26}" + "".join(f"{'top' + str(k):>10}" for k in tops))
    for label, score in schemes.items():
        order = np.argsort(score)
        print(f"{label:<26}" + "".join(f"{np.median(real[order[:k]]):>10.2f}" for k in tops))
    print(f"{'（全市场基准）':<26}" + "".join(f"{np.median(real):>10.2f}" for _ in tops))
    print(f"\n  入选票中实际箱体 >15% 的占比\n")
    print(f"{'方案':<26}" + "".join(f"{'top' + str(k):>10}" for k in tops))
    for label, score in schemes.items():
        order = np.argsort(score)
        print(f"{label:<26}"
              + "".join(f"{np.mean(real[order[:k]] > 15) * 100:>9.0f}%" for k in tops))

    print(f"\n  原阈值（漂移<{TH_A}% 带宽<{TH_B}% VR<{TH_C} 末端未突破）下 A/B/C/D 通过："
          f"{int(np.sum((drift < TH_A) & (band < TH_B) & (vr < TH_C) & (breakout <= 0)))} 只"
          f"  ← 为日线 N=80 标定的阈值，在 60m N=120 口径下失效")


# ============================================================ §3.2 n=L 退化

def exp_degenerate():
    banner("§3.2  布林周期 n 开到等于箱体长度：滚动轨道退化为静态水平箱体（W176 训练窗）")
    print(f"{'布林周期 n':>12}{'上轨抖动（相邻变化均值%）':>26}{'带宽随末端漂移敏感度':>24}")
    for n in (20, 40, 60, 90, TRAIN):
        jitter, sens = [], []
        for c in C176:
            x = X[c][:TRAIN]
            if n >= len(x):
                jitter.append(0.0)
                sens.append(0.0)
                continue
            _, std, up, _ = bands(x, n)
            jitter.append(float(np.abs(np.diff(up)).mean()) * 100)
            sens.append(float(np.abs(np.diff(2 * BK * std)).mean()) * 100)
        tag = "  ← 完全静态" if n >= TRAIN else ""
        print(f"{n:>12}{np.median(jitter):>26.4f}{np.median(sens):>24.4f}{tag}")
    print("\n  n=L 时上轨 ≡ mean+2σ、下轨 ≡ mean−2σ，两条真水平线：")
    print("    斜边矩形 → 改由漂移判据管；喇叭/收口 → 概念消失；末端局部性 → 消失")


# ============================================================ §4.6 √L 缩放

def search(x, l_min=L_MIN, l_max=L_MAX, step=1, th_drift=TH_DRIFT,
           tight=None, th_bw=None, pick="long"):
    """
    从末端搜合格箱体。tight=紧致度上限，th_bw=绝对带宽上限(%)。
    pick='long' 取最长，'tight' 取紧致度最小。返回 (L, 漂移, 带宽%, 紧致度) 或 None。
    """
    s1 = float(np.diff(x[:TRAIN]).std())
    best = None
    for L in range(l_min, min(l_max, TRAIN) + 1, step):
        drift, sd = box_of(x[:TRAIN][-L:])
        if abs(drift) >= th_drift:
            continue
        bw = 4 * sd * 100
        if th_bw is not None and bw >= th_bw:
            continue
        ratio = sd / max(s1 * np.sqrt(L / 6), 1e-12)
        if tight is not None and ratio >= tight:
            continue
        key = L if pick == "long" else -ratio
        if best is None or key > best[0]:
            best = (key, L, drift, bw, ratio)
    return best[1:] if best else None


def exp_sqrt_l():
    banner("§4.6  随机游走的箱体带宽 ∝ √L —— 固定带宽阈值筛的是长度")
    print("  布朗运动窗口内空间标准差 std = σ₁·√(L/6)，带宽 4·std ∝ √L\n")
    print(f"{'L':>6}{'理论随机带宽 %':>16}{'实测随机带宽中位 %':>20}"
          f"{'实测真实带宽中位 %':>20}{'固定8%阈值下随机通过率':>24}")
    for L in (30, 40, 60, 80, 120):
        theo = 4 * SIG1 * np.sqrt(L / 6) * 100
        rw = np.array([box_of(RW[c][:TRAIN][-L:])[1] * 4 * 100 for c in C176])
        re = np.array([box_of(X[c][:TRAIN][-L:])[1] * 4 * 100 for c in C176])
        print(f"{L:>6}{theo:>16.2f}{np.median(rw):>20.2f}{np.median(re):>20.2f}"
              f"{np.mean(rw < 8) * 100:>23.1f}%")

    print("\n  修正：紧致度 = std / (σ₁·√(L/6))，与 L 和个股波动率均无关")
    print(f"\n{'L':>6}{'真实紧致度中位':>18}{'随机游走中位':>16}{'判断':>26}")
    for L in (30, 60, 120):
        tr = np.median([box_of(X[c][:TRAIN][-L:])[1]
                        / (np.diff(X[c][:TRAIN]).std() * np.sqrt(L / 6)) for c in C176])
        rw = np.median([box_of(RW[c][:TRAIN][-L:])[1]
                        / (np.diff(RW[c][:TRAIN]).std() * np.sqrt(L / 6)) for c in C176])
        note = ("真实更紧 → 短期均值回归" if tr < rw - 0.03 else
                "真实更松 → 长期趋势主导" if tr > rw + 0.03 else "已经反了")
        print(f"{L:>6}{tr:>18.3f}{rw:>16.3f}{note:>26}")

    print("\n  信噪比 = 真实通过率 / 随机游走通过率")
    print(f"\n{'判据组合':<40}{'真实通过':>10}{'随机通过':>10}{'信噪比':>9}{'中位L':>8}")
    for label, kw in (("漂移<3% + 带宽<8%（原方案）", dict(th_bw=8.0)),
                      ("漂移<3% + 紧致度<0.7", dict(tight=0.7)),
                      ("漂移<3% + 紧致度<0.6", dict(tight=0.6)),
                      ("漂移<3% + 紧致度<0.6 + 带宽<6%", dict(tight=0.6, th_bw=6.0))):
        hr = [search(X[c], **kw) for c in C176]
        hw = [search(RW[c], **kw) for c in C176]
        pr = np.mean([h is not None for h in hr]) * 100
        pw = np.mean([h is not None for h in hw]) * 100
        lens = [h[0] for h in hr if h]
        print(f"{label:<40}{pr:>9.2f}%{pw:>9.2f}%{pr / max(pw, 1e-9):>9.2f}"
              f"{np.median(lens) if lens else float('nan'):>8.0f}")

    print(f"\n  搜索步长敏感性（漂移<3% + 带宽<8%，动态 30→120 取最长）")
    for step in (1, 5, 10):
        hr = [search(X[c], th_bw=8.0, step=step) for c in C176]
        print(f"    步长 {step:>2}：通过率 {np.mean([h is not None for h in hr]) * 100:.2f}%")


# ============================================================ §3.3 样本外配对

def oos_inside(series, c, up, lo):
    """样本外仍在箱内的比例 %。"""
    xo = series[c][TRAIN:]
    return float(np.mean((xo <= up) & (xo >= lo))) * 100


def sigma_edges(series, c, L):
    x = series[c][:TRAIN][-L:]
    mu, sd = float(x.mean()), float(x.std())
    return mu + 2 * sd, mu - 2 * sd


def exp_oos_paired():
    banner("§3.3  样本外配对验证（前 120 根搜箱体，后 56 根验证）")
    print(f"{'配置':<34}{'真实':>16}{'打乱':>16}{'净优势':>10}")
    print(f"{'':<34}{'只数  在箱内中位':>16}{'只数  在箱内中位':>16}")
    configs = (("取最长 L∈[30,120]（不设上限）", dict(pick="long", l_min=30)),
               ("取最长 L∈[30,60]", dict(pick="long", l_min=30, l_max=60)),
               ("取最长 L∈[80,120]", dict(pick="long", l_min=80)),
               ("取最紧 L∈[80,120]", dict(pick="tight", l_min=80)))
    for label, kw in configs:
        cells = []
        for series in (X, SH):
            hits = {c: search(series[c], tight=TH_TIGHT, **kw) for c in C176}
            sel = [c for c in C176 if hits[c]]
            vals = [oos_inside(series, c, *sigma_edges(series, c, hits[c][0])) for c in sel]
            cells.append((len(sel), np.median(vals) if vals else np.nan))
        print(f"{label:<34}{cells[0][0]:>8}{cells[0][1]:>8.1f}%"
              f"{cells[1][0]:>8}{cells[1][1]:>8.1f}%{cells[0][1] - cells[1][1]:>+10.1f}")
    print("\n  打乱保留波动率分布、只破坏时序结构 —— 真实减打乱才是净优势")

    banner("§3.3  机制：波动率均值回归")
    print(f"{'配置':<28}{'箱体内单根波动率':>18}{'样本外波动率':>15}{'回升倍数':>11}{'全市场':>10}")
    for label, kw in (("L∈[30,120]", dict(l_min=30)), ("L∈[80,120]", dict(l_min=80))):
        hits = {c: search(X[c], tight=TH_TIGHT, **kw) for c in C176}
        sel = [c for c in C176 if hits[c]]
        a = np.median([np.diff(X[c][:TRAIN][-hits[c][0]:]).std() for c in sel])
        b = np.median([np.diff(X[c][TRAIN:]).std() for c in sel])
        print(f"{label:<28}{a * 100:>17.3f}%{b * 100:>14.3f}%{b / a:>11.2f}x{SIG1 * 100:>9.3f}%")
    print("\n  短箱体 = 波动率暂时偏低（样本外回升，箱体必破）")
    print("  L≥80  = 结构性低波动（不回升）—— 80 根正好卡在分界上")


# ============================================================ §五 突破口径

def real_edges(series_h, series_l, c, L):
    """实际最高/最低价口径（同花顺可复现）。"""
    return float(series_h[c][:TRAIN][-L:].max()), float(series_l[c][:TRAIN][-L:].min())


def breakout(series, c, up, lo, k=10):
    """(是否向上突破, 是否假突破, 突破后 k 根方向收益%, 首次突破位置)。"""
    xo = series[c][TRAIN:]
    iu = np.flatnonzero(xo > up)
    il = np.flatnonzero(xo < lo)
    fu = iu[0] if len(iu) else 10 ** 9
    fl = il[0] if len(il) else 10 ** 9
    if min(fu, fl) >= len(xo):
        return None
    up_side = fu < fl
    i = min(fu, fl)
    j = min(i + k, len(xo) - 1)
    seg = xo[i + 1:j + 1]
    back = bool(len(seg) and ((seg <= up).any() if up_side else (seg >= lo).any()))
    sign = 1.0 if up_side else -1.0
    return up_side, back, float(sign * (xo[j] - xo[i])) * 100, int(i) + 1


def _summary(records):
    """(向上突破率%, 假突破率%, 真突破收益中位%, 首次突破位置中位)。"""
    ups = [r for r in records if r and r[0]]
    if not ups:
        return np.nan, np.nan, np.nan, np.nan
    real = [u[2] for u in ups if not u[1]]
    return (len(ups) / len(records) * 100, np.mean([u[1] for u in ups]) * 100,
            np.median(real) if real else np.nan, np.median([u[3] for u in ups]))


def exp_edge_kind():
    banner("§5.1  上下沿三种口径对照（L∈[80,120]，仅向上突破）")
    hits = {c: search(X[c], l_min=80, tight=TH_TIGHT, step=5) for c in C176}
    sel = [c for c in C176 if hits[c]]
    print(f"  基线入选 {len(sel)} 只\n")
    print(f"{'上沿口径':<26}{'箱高中位%':>11}{'向上突破率':>12}{'假突破率':>11}"
          f"{'真突破后收益中位%':>18}{'首次突破位置':>14}")
    for kind, label in (("sigma", "mean±2σ（同花顺画不出）"),
                        ("real", "实际最高/最低价 ★"),
                        ("q95", "Q95/Q05 分位")):
        spans, recs = [], []
        for c in sel:
            L = hits[c][0]
            if kind == "sigma":
                up, lo = sigma_edges(X, c, L)
            elif kind == "real":
                up, lo = real_edges(H, LO, c, L)
            else:
                x = X[c][:TRAIN][-L:]
                up, lo = float(np.quantile(x, 0.95)), float(np.quantile(x, 0.05))
            spans.append(np.exp(up - lo) - 1)
            recs.append(breakout(X, c, up, lo))
        rate, fake, ret, pos = _summary(recs)
        print(f"{label:<26}{np.median(spans) * 100:>11.2f}{rate:>11.0f}%{fake:>10.0f}%"
              f"{ret:>18.2f}{pos:>14.0f}")
    print("\n  选实际高低价：假突破率最低、真突破收益最高、同花顺上可直接画出同一条线")


def exp_length_quality():
    banner("§5.5  箱体长度对突破质量的影响（上沿 = 实际最高价）")
    print(f"{'长度档':<16}{'只数':>7}{'箱体根数中位':>13}{'≈交易日':>9}"
          f"{'向上突破率':>12}{'假突破率':>10}{'真突破收益%':>13}{'打乱假突破率':>14}")
    for label, lmin, lmax in (("L∈[30,60]", 30, 60), ("L∈[60,90]", 60, 90),
                              ("L∈[80,120]", 80, 120), ("L∈[100,120]", 100, 120)):
        hits = {c: search(X[c], l_min=lmin, l_max=lmax, tight=TH_TIGHT, step=5) for c in C176}
        sel = [c for c in C176 if hits[c]]
        if not sel:
            continue
        recs = [breakout(X, c, *real_edges(H, LO, c, hits[c][0])) for c in sel]
        hs = {c: search(SH[c], l_min=lmin, l_max=lmax, tight=TH_TIGHT, step=5) for c in C176}
        ss = [c for c in C176 if hs[c]]
        recs_s = [breakout(SH, c, *real_edges(SH_H, SH_L, c, hs[c][0])) for c in ss]
        rate, fake, ret, _ = _summary(recs)
        _, fake_s, _, _ = _summary(recs_s)
        bars = np.median([hits[c][0] for c in sel])
        print(f"{label:<16}{len(sel):>7}{bars:>13.0f}{bars / 4:>9.1f}"
              f"{rate:>11.0f}%{fake:>9.0f}%{ret:>13.2f}{fake_s:>13.0f}%")
    print("\n  60m 线 4 根 = 1 交易日。L=30 只有 7.5 个交易日，同花顺日线图上看不出箱体")


def exp_tail_position():
    banner("§5.4  末端位置效应：真实 vs 打乱（分离几何必然与市场信号）")
    groups = {}
    for tag, xs, hs, ls in (("真实", X, H, LO), ("打乱", SH, SH_H, SH_L)):
        hits = {c: search(xs[c], l_min=80, tight=TH_TIGHT, step=5) for c in C176}
        sel = [c for c in C176 if hits[c]]
        rec = {}
        for c in sel:
            L = hits[c][0]
            up, lo = real_edges(hs, ls, c, L)
            pos = (xs[c][TRAIN - 1] - lo) / max(up - lo, 1e-9)
            b = breakout(xs, c, up, lo)
            rec[c] = (pos, b if (b and b[0]) else None)
        groups[tag] = (sel, rec)

    bins = (("贴下沿 0~0.25", 0.0, 0.25), ("偏下 0.25~0.5", 0.25, 0.5),
            ("偏上 0.5~0.75 ★", 0.5, 0.75), ("贴上沿 0.75~1.0", 0.75, 1.01))
    for metric, title, fmt in (("rate", "向上突破率 %", "{:.0f}"),
                               ("fake", "假突破率 %（越低越好）", "{:.0f}"),
                               ("ret", "真突破后 10 根收益中位 %", "{:.2f}")):
        print(f"\n  {title}")
        print(f"{'末端位置档':<22}{'真实':>10}{'打乱':>10}{'净差':>10}{'真实只数':>10}")
        for name, q0, q1 in bins:
            cells, count = [], 0
            for tag in ("真实", "打乱"):
                sel, rec = groups[tag]
                grp = [c for c in sel if q0 <= rec[c][0] < q1]
                ups = [rec[c][1] for c in grp if rec[c][1]]
                if tag == "真实":
                    count = len(grp)
                if metric == "rate":
                    cells.append(len(ups) / len(grp) * 100 if grp else np.nan)
                elif metric == "fake":
                    cells.append(np.mean([u[1] for u in ups]) * 100 if ups else np.nan)
                else:
                    real = [u[2] for u in ups if not u[1]]
                    cells.append(np.median(real) if real else np.nan)
            net = cells[0] - cells[1]
            f0 = fmt.format(cells[0]) if np.isfinite(cells[0]) else "—"
            f1 = fmt.format(cells[1]) if np.isfinite(cells[1]) else "—"
            fn = f"{net:+.2f}" if np.isfinite(net) else "—"
            print(f"{name:<22}{f0:>10}{f1:>10}{fn:>10}{count:>10}")
    print("\n  「贴上沿 68% 突破率」在打乱组是 69% —— 纯几何，且真突破收益低于打乱")
    print("  偏上 0.5~0.75 是唯一假突破率与收益同时优于打乱的档位")


def exp_breakout_overall():
    banner("§七  最重要的负面结论：突破信号本身有没有净优势")
    for tag, xs, hs, ls in (("真实", X, H, LO), ("打乱", SH, SH_H, SH_L)):
        hits = {c: search(xs[c], l_min=80, tight=TH_TIGHT, step=5) for c in C176}
        sel = [c for c in C176 if hits[c]]
        recs = [breakout(xs, c, *real_edges(hs, ls, c, hits[c][0])) for c in sel]
        ups = [r for r in recs if r and r[0]]
        real = [u[2] for u in ups if not u[1]]
        print(f"  {tag}：入选 {len(sel)} 只，向上突破 {len(ups)} 只"
              f"（{len(ups) / len(sel) * 100:.0f}%），假突破率 {np.mean([u[1] for u in ups]) * 100:.0f}%，"
              f"真突破收益中位 {np.median(real):.2f}%，"
              f"全部突破收益中位 {np.median([u[2] for u in ups]):.2f}%")
    print("\n  突破时无脑买入的中位结果，真实是负的、打乱是正的 —— 突破信号没有 alpha。")
    print("  只有「真突破」才有正收益，但假突破占近六成且高于打乱对照，事前无法区分。")
    print("  实操含义：这套筛选给出的是观察名单，不是买入信号。")


def exp_ticket_count():
    banner("§5.5  票数分档（L∈[80,120]，上沿 = 实际最高价）")
    print(f"{'参数组合':<44}{'入选只数':>10}{'箱高中位%':>11}{'向上突破率':>12}{'假突破率':>10}")
    for tight, bw, drift in ((0.6, None, 3.0), (0.6, 8.0, 3.0), (0.6, 6.0, 3.0),
                             (0.5, 6.0, 3.0), (0.5, 5.0, 2.0), (0.45, 4.5, 2.0),
                             (0.4, 4.0, 1.5)):
        hits = {c: search(X[c], l_min=80, th_drift=drift, tight=tight, th_bw=bw, step=5)
                for c in C176}
        sel = [c for c in C176 if hits[c]]
        tag = f"紧致度<{tight}  带宽<{bw if bw else '不限'}%  漂移<{drift}%"
        if not sel:
            print(f"{tag:<44}{0:>10}")
            continue
        spans, recs = [], []
        for c in sel:
            up, lo = real_edges(H, LO, c, hits[c][0])
            spans.append(np.exp(up - lo) - 1)
            recs.append(breakout(X, c, up, lo))
        rate, fake, _, _ = _summary(recs)
        print(f"{tag:<44}{len(sel):>10}{np.median(spans) * 100:>11.2f}{rate:>11.0f}%{fake:>9.0f}%")
    print("\n  反直觉：收紧参数假突破率反而上升（窄箱体突破幅度小，易被噪声打穿又回来）")


# ============================================================ §七 噪声指标

def exp_noise_filters():
    banner("§七  噪声过滤指标：必须与打乱对照配对，否则结论相反")
    for tag, xs, hs, ls in (("真实", X, H, LO), ("打乱", SH, SH_H, SH_L)):
        hits = {c: search(xs[c], l_min=80, tight=TH_TIGHT, step=5) for c in C176}
        sel = [c for c in C176 if hits[c]]
        base = np.median([oos_inside(xs, c, *real_edges(hs, ls, c, hits[c][0])) for c in sel])
        feats = {}
        for c in sel:
            L = hits[c][0]
            up, lo = real_edges(hs, ls, c, L)
            lh, ll = hs[c][:TRAIN][-L:], ls[c][:TRAIN][-L:]
            rg = np.maximum(lh - ll, 1e-9)
            eps = 0.05 * max(up - lo, 1e-9)
            park = np.sqrt(np.mean(rg ** 2) / (4 * np.log(2)))
            feats[c] = (min(int(np.count_nonzero(lh >= up - eps)),
                            int(np.count_nonzero(ll <= lo + eps))),
                        park / max(float(xs[c][:TRAIN][-L:].std()), 1e-12),
                        float(rg.max() / max(float(np.median(rg)), 1e-9)))
        cuts = [np.percentile([feats[c][i] for c in sel], q) for i, q in ((0, 50), (1, 50), (2, 50))]
        keep = [c for c in sel if feats[c][0] >= cuts[0]
                and feats[c][1] <= cuts[1] and feats[c][2] <= cuts[2]]
        v = np.median([oos_inside(xs, c, *real_edges(hs, ls, c, hits[c][0])) for c in keep])
        print(f"  {tag}：基线 {len(sel)} 只 / {base:.1f}%   →   "
              f"三重过滤（触碰+Parkinson+单根异动）后 {len(keep)} 只 / {v:.1f}%   提升 {v - base:+.1f}")
    print("\n  两边提升幅度相近 → 过滤的是几何噪声，不是市场结构噪声，净增量 ≈ 0")
    print("  只看真实组的提升会以为找到宝了 —— 这是必须做配对的原因")

    print("\n  成交量类指标（目标A 在箱内口径，各取最严 30%）")
    print(f"{'指标':<26}{'真实 Δ基线':>13}{'打乱 Δ基线':>13}{'净增量':>10}")
    keys = ("量能收缩 后/前", "相对量能 箱内/箱前", "量能稳定度 σ(lnV)",
            "量价脱钩 |corr|", "单根天量 max/中位")
    deltas = {k: [] for k in keys}
    for tag, xs, hs, ls in (("真实", X, H, LO), ("打乱", SH, SH_H, SH_L)):
        hits = {c: search(xs[c], l_min=80, tight=TH_TIGHT, step=5) for c in C176}
        sel = [c for c in C176 if hits[c]]
        base = np.median([oos_inside(xs, c, *real_edges(hs, ls, c, hits[c][0])) for c in sel])
        rows = {}
        for c in sel:
            L = hits[c][0]
            v = DATA[c][4][:TRAIN][-L:]
            if not np.isfinite(v).all() or (v <= 0).any():
                continue
            earlier = DATA[c][4][:TRAIN][:max(TRAIN - L, 1)]
            half = L // 2
            dprice = np.abs(np.diff(xs[c][:TRAIN][-L:]))
            rows[c] = (float(v[half:].mean() / max(v[:half].mean(), 1e-9)),
                       float(v.mean() / max(earlier.mean(), 1e-9)) if len(earlier) > 5 else np.nan,
                       float(np.log(v).std()),
                       abs(float(np.corrcoef(dprice, v[1:])[0, 1]))
                       if L > 3 and v[1:].std() > 0 else np.nan,
                       float(v.max() / max(float(np.median(v)), 1e-9)))
        pool = list(rows)
        for i, key in enumerate(keys):
            vals = np.array([rows[c][i] for c in pool], dtype=float)
            ok = np.isfinite(vals)
            if ok.sum() < 30:
                deltas[key].append(np.nan)
                continue
            cut = np.percentile(vals[ok], 30)
            keep = [c for c, val, k in zip(pool, vals, ok) if k and val <= cut]
            v = np.median([oos_inside(xs, c, *real_edges(hs, ls, c, hits[c][0])) for c in keep])
            deltas[key].append(v - base)
    for key in keys:
        d = deltas[key]
        flag = "  ⚠️ 机制是打乱组下降" if len(d) == 2 and d[0] >= -0.1 and d[1] < -1 else ""
        print(f"{key:<26}{d[0]:>+13.1f}{d[1]:>+13.1f}{d[0] - d[1]:>+10.1f}{flag}")


# ============================================================ 主流程

if __name__ == "__main__":
    for fn in (exp_edges_vs_real, exp_local_vs_global, exp_inside_ratio, exp_fair_compare,
               exp_degenerate, exp_sqrt_l, exp_oos_paired, exp_edge_kind,
               exp_length_quality, exp_tail_position, exp_breakout_overall,
               exp_ticket_count, exp_noise_filters):
        fn()
