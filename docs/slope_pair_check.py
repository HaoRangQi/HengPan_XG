"""
横盘思路 4（点对斜率统计法）的验证脚本。

对照原判据（点对斜率均值≈0 且离散度低）与修正判据 A/B/C/D，
用 8 个人工标注结论的合成场景跑对照。纯计算，不联网、不读写项目数据。

用法：api/.venv/bin/python docs/slope_pair_check.py
配套文档：横盘思路4-点对斜率统计法.md
"""
import itertools
import time

import numpy as np

N = 80          # 回看根数
SEED = 42       # 固定种子，保证各表格共用同一份数据

_CACHE = {}


# ---------------------------------------------------------------- 场景构造

def scenarios():
    """8 个合成场景，返回 {名称: (80 个实体中点, 人工标注是否横盘)}。"""
    if _CACHE:
        return _CACHE
    rng = np.random.default_rng(SEED)
    t = np.arange(N)

    # A 真横盘：OU 均值回复，箱体约 4%
    price, path = 10.0, np.zeros(N)
    for k in range(N):
        price += 0.15 * (10.0 - price) + rng.normal(0, 0.05)
        path[k] = price
    _CACHE["A 真横盘 箱体4% 均值回复"] = (path, True)

    # B 锯齿横盘：箱体同样 4%，但每根来回跳
    _CACHE["B 锯齿横盘 箱体4% 高频来回"] = (
        10.0 + 0.2 * ((-1.0) ** t) + rng.normal(0, 0.01, N), True)

    # C 平滑缓涨 +20%，几乎无噪声
    _CACHE["C 平滑缓涨 +20%"] = (
        np.linspace(10.0, 12.0, N) + rng.normal(0, 0.01, N), False)

    # D 倒 V 过山车：涨 15% 再跌回原点
    peak = 10.0 + 1.5 * (1 - np.abs(t - (N - 1) / 2) / ((N - 1) / 2))
    _CACHE["D 倒V过山车 涨15%跌回 无噪"] = (peak, False)
    _CACHE["D2 倒V过山车 带噪声"] = (peak + rng.normal(0, 0.06, N), False)

    # E 宽幅震荡：箱体 20%，低频摆动
    _CACHE["E 宽幅震荡 箱体20% 低频"] = (
        10.0 + 1.0 * np.sin(2 * np.pi * t / 26) + rng.normal(0, 0.02, N), False)

    # F 温和上升通道 +8%（边界情况）
    _CACHE["F 温和上升通道 +8%"] = (
        np.linspace(10.0, 10.8, N) + rng.normal(0, 0.06, N), False)

    # G 横盘 74 根后末端 6 根拉升 9%
    tail = np.full(N, 10.0) + rng.normal(0, 0.06, N)
    tail[-6:] = 10.0 + np.linspace(0.1, 0.9, 6)
    _CACHE["G 横盘后末端拉升"] = (tail, False)

    return _CACHE


# ---------------------------------------------------------- 原思路：点对斜率

def pair_slopes_random(m, n_pairs=3000, generator=None):
    """随机取点对，标准化斜率（除以起点价，单位 %/根）。"""
    gen = generator or np.random.default_rng(SEED)
    i = gen.integers(0, N, n_pairs)
    j = gen.integers(0, N, n_pairs)
    keep = i != j
    lo, hi = np.minimum(i, j)[keep], np.maximum(i, j)[keep]
    return (m[hi] - m[lo]) / (hi - lo) / m[lo] * 100


def verdict_original(m, max_abs_mean=0.05, max_std=0.35):
    s = pair_slopes_random(m)
    return abs(s.mean()) < max_abs_mean and s.std() < max_std, s.mean(), s.std()


def slope_std_by_gap(m, gaps=(1, 5, 20, 60)):
    """同一序列按间隔 k 分层的斜率 std，用于展示量纲污染。"""
    return {k: ((m[k:] - m[:-k]) / k / m[:-k] * 100).std() for k in gaps}


# ----------------------------------------------------------- 修正判据 A/B/C/D

def metrics(m):
    """一次算齐四项指标：周期漂移%、去趋势分位带宽%、最大方差比、末端突破度。"""
    x = np.log(m)
    n = len(x)
    i, j = np.triu_indices(n, k=1)
    beta = np.median((x[j] - x[i]) / (j - i))              # A: Theil-Sen

    r = x - beta * np.arange(n)                            # B: 去趋势残差
    lo, hi = np.quantile(r, 0.05), np.quantile(r, 0.95)
    band = hi - lo

    d1_var = np.diff(x).var()                              # C: 方差比
    vr = max((x[k:] - x[:-k]).var() / (k * d1_var) for k in (10, 20, 40))

    breakout = max(r[-1] - hi, lo - r[-1]) / max(band, 1e-9)   # D: 末端突破度
    centered = abs(r[-1] - (lo + hi) / 2) / max(band / 2, 1e-9)
    return beta * n * 100, band * 100, vr, breakout, centered


def checks(m, max_drift=2.0, max_band=4.5, max_vr=0.6, tail="breakout"):
    """四条判据各自的通过情况。tail 选 breakout（未突破）或 centered（居中）。"""
    drift, band, vr, breakout, centered = metrics(m)
    return {"A漂移": abs(drift) < max_drift, "B带宽": band < max_band,
            "C方差比": vr < max_vr,
            "D末端": breakout <= 0.0 if tail == "breakout" else centered < 0.8}


def verdict_fixed(m, tail="breakout", **th):
    ok = all(checks(m, tail=tail, **th).values())
    return (ok, *metrics(m))


# ------------------------------------------------------------------- 报表

def banner(text):
    print(f"\n{'=' * 100}\n{text}\n{'=' * 100}")


def mark(got, truth):
    return ("横盘" if got else "淘汰") + ("" if got == truth else "✗")


banner("表1  斜率离散度被『间隔 k』主导 —— 同一序列按 k 分层的斜率 std (%/根)")
print(f"{'场景':<30}{'k=1':>11}{'k=5':>11}{'k=20':>11}{'k=60':>11}{'k1/k60':>11}")
for name, (m, _) in scenarios().items():
    g = slope_std_by_gap(m)
    print(f"{name:<30}{g[1]:>11.3f}{g[5]:>11.3f}{g[20]:>11.3f}{g[60]:>11.3f}"
          f"{g[1] / max(g[60], 1e-9):>10.0f}x")

banner("表2  原判据 vs 修正判据（末端用『未突破』口径）")
print(f"{'场景':<30}{'真实':>5}|{'斜率均值':>9}{'斜率std':>9}{'原判':>7}|"
      f"{'漂移%':>8}{'带宽%':>8}{'VR':>8}{'突破度':>8}{'新判':>7}")
bad_old = bad_new = 0
for name, (m, truth) in scenarios().items():
    old, s_mean, s_std = verdict_original(m)
    new, drift, band, vr, breakout, _ = verdict_fixed(m)
    bad_old += old != truth
    bad_new += new != truth
    print(f"{name:<30}{'横盘' if truth else '淘汰':>5}|{s_mean:>9.3f}{s_std:>9.3f}"
          f"{mark(old, truth):>8}|{drift:>8.2f}{band:>8.2f}{vr:>8.2f}{breakout:>8.2f}"
          f"{mark(new, truth):>8}")
print(f"\n{'误判数':>36}：原判据 {bad_old}/{len(scenarios())}，"
      f"修正判据 {bad_new}/{len(scenarios())}")

banner("表3  随机抽样的不可复现性 —— 同一序列重复 20 轮随机取 3000 对")
print(f"{'场景':<30}{'std最小':>10}{'std最大':>10}{'极差':>10}{'判定翻转':>10}")
for name, (m, _) in scenarios().items():
    stds = [pair_slopes_random(m, 3000, np.random.default_rng(seed)).std()
            for seed in range(20)]
    flipped = len({s < 0.35 for s in stds}) > 1
    print(f"{name:<30}{min(stds):>10.3f}{max(stds):>10.3f}"
          f"{max(stds) - min(stds):>10.3f}{'是 ←' if flipped else '否':>10}")

banner("表4  全枚举 vs 随机抽样：耗时")
m = scenarios()["A 真横盘 箱体4% 均值回复"][0]
x = np.log(m)
i, j = np.triu_indices(N, k=1)
for label, fn in (("全枚举 3160 对", lambda: np.median((x[j] - x[i]) / (j - i))),
                  ("随机 3000 对", lambda: pair_slopes_random(m, 3000).mean()),
                  ("修正判据 A+B+C+D", lambda: verdict_fixed(m))):
    t0 = time.perf_counter()
    for _ in range(200):
        fn()
    per = (time.perf_counter() - t0) / 200
    print(f"{label:<22}{per * 1e6:>8.0f} µs/只   全市场 5000 只约 {per * 5000:>5.2f} s")

banner("表5  带宽阈值标定：去趋势分位带宽 vs 全幅 max-min")
for name, (m, truth) in scenarios().items():
    _, band, _, _, _ = metrics(m)
    raw = (m.max() - m.min()) / m.min() * 100
    print(f"{name:<30}{'横盘' if truth else '淘汰':>5}   分位带宽 {band:>6.2f}%   "
          f"全幅 {raw:>6.2f}%   压缩 {(1 - band / raw) * 100:>4.0f}%")

banner("表6  末端约束两种口径：『未突破』 vs 『居中』")
print(f"{'场景':<30}{'真实':>5}|{'突破度':>9}{'居中度':>9}|{'未突破':>9}{'居中':>9}")
n_bo = n_ct = 0
for name, (m, truth) in scenarios().items():
    v_bo, _, _, _, breakout, centered = verdict_fixed(m, tail="breakout")
    v_ct = verdict_fixed(m, tail="centered")[0]
    n_bo += v_bo != truth
    n_ct += v_ct != truth
    print(f"{name:<30}{'横盘' if truth else '淘汰':>5}|{breakout:>9.2f}{centered:>9.2f}|"
          f"{mark(v_bo, truth):>10}{mark(v_ct, truth):>10}")
print(f"\n{'误判数':>36}：未突破口径 {n_bo}/{len(scenarios())}，"
      f"居中口径 {n_ct}/{len(scenarios())}")


# --------------------------------------------------------------- 判据消融

CHECKS = ("A漂移", "B带宽", "C方差比", "D末端")


def sub_verdict(m, use):
    """只用 use 里列出的判据做判定，用于消融。阈值与 checks() 共用，不重复定义。"""
    got = checks(m)
    return all(got[k] for k in use)


banner("表7  判据消融：穷举 15 个子集，看哪些判据真正不可替代")
print(f"{'保留的判据':<24}{'误判':>7}   漏掉的场景")
rows = []
for size in range(1, len(CHECKS) + 1):
    for use in itertools.combinations(CHECKS, size):
        bad = [n for n, (m, t) in scenarios().items() if sub_verdict(m, use) != t]
        rows.append((len(bad), len(use), use, bad))
for n_bad, n_use, use, bad in sorted(rows):
    star = " ★最小充分集" if n_bad == 0 and n_use <= 2 else ""
    print(f"{'+'.join(k[0] for k in use):<24}{n_bad:>5}/8   "
          f"{'、'.join(x[:14] for x in bad) or '—'}{star}")

banner("表8  每个应淘汰场景被哪几条判据拦下（『独家』= 删掉它就漏网）")
for name, (m, truth) in scenarios().items():
    if truth:
        continue
    blockers = [k for k, ok in checks(m).items() if not ok]
    solo = "  ← 独家" if len(blockers) == 1 else ""
    print(f"  {name:<28} 被拦于：{'、'.join(blockers)}{solo}")
