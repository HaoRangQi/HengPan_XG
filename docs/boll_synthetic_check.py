"""
横盘思路 5（布林轨道箱体形态法）的验证脚本。

复用 docs/slope_pair_check.py 的 8 个合成场景（同种子，保证可比），
另加 3 个专门针对布林带方案的对抗场景，对照：
  - 用户原判据（上下轨水平 + 带宽恒定）
  - 等价分解判据（中轨斜率 + 带宽斜率）
  - 补全判据（加带宽绝对水平）
以及验证两条结构性结论：自由度只有 2、带宽斜率的统计功效不足。

用法：api/.venv/bin/python docs/boll_synthetic_check.py
"""
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

N = 80          # 回看根数，与现有模式对齐
SEED = 42       # 与 slope_pair_check.py 同种子
BOLL_N = 20     # 布林窗口
BOLL_K = 2.0    # 布林倍数

_CACHE = {}


# ---------------------------------------------------------------- 场景构造

def scenarios():
    """11 个合成场景，返回 {名称: (80 个实体中点, 人工标注是否横盘)}。"""
    if _CACHE:
        return _CACHE
    rng = np.random.default_rng(SEED)
    t = np.arange(N)

    # ---- 以下 8 个与 docs/slope_pair_check.py 完全一致（同序同种子）----
    price, path = 10.0, np.zeros(N)
    for k in range(N):
        price += 0.15 * (10.0 - price) + rng.normal(0, 0.05)
        path[k] = price
    _CACHE["A 真横盘 箱体4%"] = (path, True)
    _CACHE["B 锯齿横盘 箱体4%"] = (10.0 + 0.2 * ((-1.0) ** t) + rng.normal(0, 0.01, N), True)
    _CACHE["C 平滑缓涨 +20%"] = (np.linspace(10.0, 12.0, N) + rng.normal(0, 0.01, N), False)
    peak = 10.0 + 1.5 * (1 - np.abs(t - (N - 1) / 2) / ((N - 1) / 2))
    _CACHE["D 倒V过山车 无噪"] = (peak, False)
    _CACHE["D2 倒V过山车 带噪"] = (peak + rng.normal(0, 0.06, N), False)
    _CACHE["E 宽幅震荡 箱体20%"] = (10.0 + 1.0 * np.sin(2 * np.pi * t / 26) + rng.normal(0, 0.02, N), False)
    _CACHE["F 温和上升通道 +8%"] = (np.linspace(10.0, 10.8, N) + rng.normal(0, 0.06, N), False)
    tail = np.full(N, 10.0) + rng.normal(0, 0.06, N)
    tail[-6:] = 10.0 + np.linspace(0.1, 0.9, 6)
    _CACHE["G 横盘后末端拉升"] = (tail, False)

    # ---- 新增 3 个：专打布林带方案的已知弱点 ----
    # H 高频巨震：中轨完全水平、带宽完全恒定，但箱体 30%。打「缺带宽水平约束」
    _CACHE["H 高频巨震 箱体30%"] = (10.0 + 1.5 * ((-1.0) ** t) + rng.normal(0, 0.02, N), False)
    # I 单根插针：79 根横盘 + 1 根 +13% 当日回落。打「滚动窗口滑出伪影」
    spike = np.full(N, 10.0) + rng.normal(0, 0.05, N)
    spike[40] = 11.3
    _CACHE["I 单根插针 其余横盘"] = (spike, True)
    # J 收敛三角：中枢不变、振幅 8%→1%。打「排除收口是否合理」
    _CACHE["J 收敛三角 8%->1%"] = (10.0 + np.linspace(0.40, 0.05, N) * ((-1.0) ** t), True)

    return _CACHE


# ------------------------------------------------------------ 布林带与估计量

def bands(m, n=BOLL_N, k=BOLL_K, log=True):
    """返回 (中轨, 标准差, 上轨, 下轨)。log=True 时在 ln 价格空间计算（天然无量纲）。"""
    x = np.log(m) if log else np.asarray(m, dtype=float)
    window = sliding_window_view(x, n)
    mid = window.mean(axis=1)
    std = window.std(axis=1)          # ddof=0，与 TA-Lib 一致
    return mid, std, mid + k * std, mid - k * std


def ols_slope(y):
    """最小二乘斜率。"""
    t = np.arange(len(y), dtype=float)
    return float(np.polyfit(t, y, 1)[0])


def theil_sen(y):
    """Theil-Sen 稳健斜率（全枚举点对中位数），与思路 4 判据 A 同口径。"""
    i, j = np.triu_indices(len(y), k=1)
    return float(np.median((y[j] - y[i]) / (j - i)))


def detrended_band(m):
    """思路 4 判据 B：去趋势 5%/95% 分位带宽（%）。用于和布林带宽对照。"""
    x = np.log(m)
    beta = theil_sen(x)
    r = x - beta * np.arange(len(x))
    return float(np.quantile(r, 0.95) - np.quantile(r, 0.05)) * 100


def boll_metrics(m):
    """布林形态的全部指标。log 空间，所有量无量纲。"""
    mid, std, upper, lower = bands(m)
    L = len(mid)

    # 轨道斜率（OLS，用于验证恒等式）→ 换算成「窗口内累计漂移 %」
    bu, bl, bm = ols_slope(upper), ols_slope(lower), ols_slope(mid)
    # 中轨漂移：稳健口径，与思路 4 判据 A 对齐
    drift = theil_sen(mid) * L * 100
    # 带宽：log 空间下 BW = 2kσ 即相对带宽
    bw = 2 * BOLL_K * std
    bw_level = float(bw.mean()) * 100                       # 平均带宽 %
    # 喇叭度：带宽的相对变化（>0 开口，<0 收口），稳健斜率抗单点伪影
    flare = theil_sen(std) * L / max(float(np.median(std)), 1e-12)
    # 带宽稳定度：四分位相对离散
    stab = float(np.quantile(std, 0.75) - np.quantile(std, 0.25)) / max(float(np.median(std)), 1e-12)
    return dict(bu=bu * L * 100, bl=bl * L * 100, bm=bm * L * 100, drift=drift,
                bw_level=bw_level, flare=flare, stab=stab, std_series=std, bw=bw)


# --------------------------------------------------------------------- 判据

TH_DRIFT = 2.0      # 中轨/轨道漂移上限 %（与思路 4 判据 A 同值）
TH_FLARE = 0.30     # 喇叭度上限（带宽相对变化 30%）
TH_BW = 5.5         # 平均带宽上限 %（由判据 B 的 4.5% 换算，见 §换算说明）


def verdict_user(g):
    """用户原判据：上轨水平 + 下轨水平 + 带宽恒定。无带宽水平约束。"""
    return abs(g["bu"]) < TH_DRIFT and abs(g["bl"]) < TH_DRIFT and abs(g["flare"]) < TH_FLARE


def verdict_split(g):
    """等价分解：中轨水平 + 带宽恒定。应与 verdict_user 判定几乎一致。"""
    return abs(g["drift"]) < TH_DRIFT and abs(g["flare"]) < TH_FLARE


def verdict_full(g):
    """补全：中轨水平 + 带宽水平（新增）+ 带宽恒定。"""
    return abs(g["drift"]) < TH_DRIFT and g["bw_level"] < TH_BW and abs(g["flare"]) < TH_FLARE


def verdict_nofl(g):
    """去掉「带宽恒定」：中轨水平 + 带宽水平。测 flare 这条判据的净贡献。"""
    return abs(g["drift"]) < TH_DRIFT and g["bw_level"] < TH_BW


# --------------------------------------------------------------------- 报表

def banner(text):
    print(f"\n{'=' * 104}\n{text}\n{'=' * 104}")


def mark(got, truth):
    return ("横盘" if got else "淘汰") + ("" if got == truth else " ✗")


SC = scenarios()
G = {name: boll_metrics(m) for name, (m, _) in SC.items()}

banner("表1  自由度验证：布林四形态只有 2 个独立量  (OLS 斜率，单位：窗口内累计漂移 %)")
print(f"{'场景':<26}{'上轨βU':>9}{'下轨βL':>9}{'中轨βM':>9}"
      f"{'(βU+βL)/2':>11}{'误差':>10}{'βU−βL':>9}{'2k·βσ':>9}{'误差':>10}")
for name, (m, _) in SC.items():
    g = G[name]
    mid, std, _, _ = bands(m)
    L = len(mid)
    half = (g["bu"] + g["bl"]) / 2
    diff = g["bu"] - g["bl"]
    twok = 2 * BOLL_K * ols_slope(std) * L * 100
    print(f"{name:<26}{g['bu']:>9.2f}{g['bl']:>9.2f}{g['bm']:>9.2f}"
          f"{half:>11.2f}{abs(half - g['bm']):>10.2e}{diff:>9.2f}{twok:>9.2f}{abs(diff - twok):>10.2e}")
print("\n  → (βU+βL)/2 ≡ βM 且 βU−βL ≡ 2k·βσ，误差全为浮点级。")
print("    『上轨水平』与『下轨水平』不是两个独立条件，其和差才独立 → 真实自由度 = (中轨斜率, σ斜率)。")

banner("表2  判据对照：用户原判据 / 等价分解 / 补全 / 去掉带宽恒定")
print(f"{'场景':<26}{'真实':>5}|{'βU':>8}{'βL':>8}{'中轨漂移':>9}{'平均带宽':>9}"
      f"{'喇叭度':>8}{'稳定度':>8}|{'用户':>7}{'分解':>7}{'补全':>7}{'去flare':>8}")
bad = {"用户": 0, "分解": 0, "补全": 0, "去flare": 0}
for name, (m, truth) in SC.items():
    g = G[name]
    v = {"用户": verdict_user(g), "分解": verdict_split(g),
         "补全": verdict_full(g), "去flare": verdict_nofl(g)}
    for k in bad:
        bad[k] += v[k] != truth
    print(f"{name:<26}{'横盘' if truth else '淘汰':>5}|{g['bu']:>8.2f}{g['bl']:>8.2f}"
          f"{g['drift']:>9.2f}{g['bw_level']:>9.2f}{g['flare']:>8.2f}{g['stab']:>8.2f}|"
          f"{mark(v['用户'], truth):>8}{mark(v['分解'], truth):>8}"
          f"{mark(v['补全'], truth):>8}{mark(v['去flare'], truth):>9}")
print(f"\n  误判数：用户原判据 {bad['用户']}/{len(SC)}   等价分解 {bad['分解']}/{len(SC)}   "
      f"补全 {bad['补全']}/{len(SC)}   去掉带宽恒定 {bad['去flare']}/{len(SC)}")

banner("表3  布林带宽 vs 思路4判据B（去趋势分位带宽）—— 测两者是否冗余")
print(f"{'场景':<26}{'布林带宽2kσ %':>15}{'判据B分位带宽 %':>17}{'比值':>9}")
x_boll, x_b = [], []
for name, (m, _) in SC.items():
    a, b = G[name]["bw_level"], detrended_band(m)
    x_boll.append(a)
    x_b.append(b)
    print(f"{name:<26}{a:>15.2f}{b:>17.2f}{a / max(b, 1e-9):>9.2f}")
r = np.corrcoef(x_boll, x_b)[0, 1]
print(f"\n  相关系数 r = {r:.4f}   Spearman 秩相关 = "
      f"{np.corrcoef(np.argsort(np.argsort(x_boll)), np.argsort(np.argsort(x_b)))[0, 1]:.4f}")
print(f"  正态下换算：Q95−Q05 = 3.29σ，2kσ = {2 * BOLL_K:.0f}σ → 布林阈值 = B阈值 × "
      f"{2 * BOLL_K / 3.29:.2f}（4.5% → {4.5 * 2 * BOLL_K / 3.29:.2f}%）")

banner("表4  带宽斜率的统计功效：σ 序列自相关与有效自由度")
print(f"{'场景':<26}{'σ序列长度':>10}{'lag-1自相关':>12}{'lag-5':>9}"
      f"{'有效独立样本':>13}{'喇叭度标准误':>14}{'信噪比':>8}")
for name, (m, _) in SC.items():
    s = G[name]["std_series"]
    d = s - s.mean()
    ac1 = float(np.dot(d[:-1], d[1:]) / max(np.dot(d, d), 1e-30))
    ac5 = float(np.dot(d[:-5], d[5:]) / max(np.dot(d, d), 1e-30))
    n_eff = len(s) * (1 - ac1) / (1 + ac1) if ac1 < 1 else 1.0
    # OLS 斜率标准误，按有效样本数折算，再换算到喇叭度量纲
    t = np.arange(len(s), dtype=float)
    resid = s - np.polyval(np.polyfit(t, s, 1), t)
    se = np.sqrt(np.sum(resid ** 2) / max(len(s) - 2, 1)) / max(np.sqrt(np.sum((t - t.mean()) ** 2)), 1e-12)
    se_eff = se * np.sqrt(len(s) / max(n_eff, 1.0))
    se_flare = se_eff * len(s) / max(float(np.median(s)), 1e-12)
    print(f"{name:<26}{len(s):>10}{ac1:>12.3f}{ac5:>9.3f}{n_eff:>13.1f}"
          f"{se_flare:>14.3f}{abs(G[name]['flare']) / max(se_flare, 1e-9):>8.2f}")
print(f"\n  理论：布林窗口 n={BOLL_N} 时相邻 σ 共用 {BOLL_N - 1}/{BOLL_N} 的数据 → 极高自相关；")
print(f"        非重叠块数 = (N−n+1)/n = {(N - BOLL_N + 1) / BOLL_N:.1f} 个。信噪比 < 2 表示喇叭度与 0 无法区分。")

banner("表5  滚动窗口滑出伪影：场景 I（单根 +13% 插针，其余 79 根横盘）")
s = G["I 单根插针 其余横盘"]["std_series"]
mid_i, _, _, _ = bands(SC["I 单根插针 其余横盘"][0])
print(f"  插针在第 40 根；σ序列第 i 位覆盖原始 [i, i+{BOLL_N - 1}] "
      f"→ 第 {40 - BOLL_N + 1} 位插针进窗口，第 {40 + 1} 位插针出窗口")
print(f"\n{'σ序列位置':>10}{'σ值':>10}{'环比变化':>10}   {'说明':<40}")
for pos in (18, 20, 21, 22, 39, 40, 41, 42):
    if pos < len(s):
        chg = (s[pos] / s[pos - 1] - 1) * 100 if pos else 0.0
        note = ("插针进入窗口 ← 假开口" if pos == 21 else
                "插针滑出窗口 ← 假收口" if pos == 41 else
                "插针在窗口内，价格无事发生" if 21 < pos < 41 else "")
        print(f"{pos:>10}{s[pos]:>10.4f}{chg:>9.1f}%   {note:<40}")
print(f"\n  σ 峰值/谷值 = {s.max() / s.min():.2f}x，全部由一根 K 线的进出窗口造成，期间价格中枢未变。")
print(f"  该场景喇叭度 = {G['I 单根插针 其余横盘']['flare']:.3f}，"
      f"带宽稳定度 = {G['I 单根插针 其余横盘']['stab']:.3f}（真横盘票被伪影推高）")

banner("表6  判据消融：布林三条判据各自的净贡献（11 场景）")
CH = {"中轨水平": lambda g: abs(g["drift"]) < TH_DRIFT,
      "带宽水平": lambda g: g["bw_level"] < TH_BW,
      "带宽恒定": lambda g: abs(g["flare"]) < TH_FLARE}
import itertools
rows = []
for size in range(1, 4):
    for use in itertools.combinations(CH, size):
        wrong = [n for n, (m, t) in SC.items() if all(CH[k](G[n]) for k in use) != t]
        rows.append((len(wrong), len(use), use, wrong))
print(f"{'保留的判据':<30}{'误判':>7}   误判场景")
for n_bad, n_use, use, wrong in sorted(rows):
    star = " ★最小充分集" if n_bad == min(r[0] for r in rows) and n_use <= 2 else ""
    print(f"{'+'.join(use):<30}{n_bad:>5}/{len(SC)}   "
          f"{'、'.join(w[:16] for w in wrong) or '—'}{star}")

banner("表7  收口形态的判定分歧：场景 J（收敛三角，中枢不变，振幅 8%→1%）")
gj = G["J 收敛三角 8%->1%"]
print(f"  中轨漂移 {gj['drift']:.2f}%   平均带宽 {gj['bw_level']:.2f}%   "
      f"喇叭度 {gj['flare']:.2f}（负 = 收口）   稳定度 {gj['stab']:.2f}")
print(f"  用户判据（排除收口）→ {'入选' if verdict_user(gj) else '淘汰'}")
print(f"  去掉带宽恒定        → {'入选' if verdict_nofl(gj) else '淘汰'}")
print("  → 收敛三角是教科书级的突破前形态。『排除收口』是策略选择，不是数学对错。")
