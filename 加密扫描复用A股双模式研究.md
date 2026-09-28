# 加密扫描复用 A 股双模式研究 · 平台扫描优先

> 日期：2026-09-28
> 范围：调研加密永续能否复用 A 股现有的两种横盘模式（**平台扫描** 与 **横盘选股**），按用户要求以「平台扫描」为第一重点。
> 前置文档：上级目录《加密货币横盘扫描数据源研究.md》（数据源、接口、字段、波动实测）、《加密永续本地存储方案-1小时线.md》（表结构、同步、读取层）。本文只讲扫描逻辑的复用，不重复那两份内容。
> 本次调研**未改动任何项目文件**，所有数字为本机实测。

**一句话结论**：平台扫描的计算内核完全市场无关，可零改动吃加密数据；真正的工作量在取数编排层和参数重标定。但实测发现一个必须先决策的问题——**平台扫描搬到小时线上会退化成单条件筛选**，这会削弱「两种模式各有优势」的前提。

---

## 目录

1. 结论速览
2. 两种模式的实现现状
3. 分层可复用性（实测逐列核对）
4. 关键发现一：小时线上多维度筛选退化
5. 关键发现二：参数必须按 category 分两套
6. 关键发现三：低位判断的时间尺度失真
7. 关键发现四：`box_detector` 的两处 A 股硬编码
8. 改造方案
9. 两种模式在加密上的定位
10. 前置阻塞与待拍板项
11. 复现脚本

---

## 1. 结论速览

| 维度 | 结论 |
|---|---|
| 计算内核（`api/analyzers/`） | **零改动可用**。逐列核对确认只吃 OHLCV + date，窗口按行数切片，不碰 `turn`/`isST`/`amount`/板块代码 |
| 取数编排（`platform_scanner.py`） | **需改造**。死绑 baostock，要抽成可注入的 loader；横盘模块已有现成范本 |
| 基本面筛选 | **不可用**。依赖 `peTTM`/`pbMRQ`/`pctChg`，加密必须关掉 |
| 行业分散过滤 | **降级可用**。加密无行业，用 `category`（perpetual / tradifi）顶替 |
| 参数 | **必须重标定，且按两类资产各设一套**，否则 TradFi 会淹没加密 |
| 低位 / 下跌判断 | **第一版建议关掉**。参数名叫「天」但实际按「根」切，小时线上约束恒为真 |
| 前端 | **可复用**。项目里已有验证过的市场描述符模式（`src/views/data/markets.js`） |
| 前置阻塞 | `crypto.db` 四张数据表全 0 行，本机出口 451，同步未跑通 |

---

## 2. 两种模式的实现现状

| | 平台扫描 | 横盘选股 |
|---|---|---|
| 前端路由 | `/platform` → `src/views/ScanView.vue` | `/` → `src/hengpan/HengpanScanView.vue` |
| 后端入口 | `api/index.py:254` `/api/scan/start`（**未模块化，直接写在 index.py**） | `api/hengpan/router.py:169` `/api/hengpan/scan/start` |
| 扫描器 | `api/platform_scanner.py:159` `scan_stocks` | `api/hengpan/scanner.py:173` `scan_anchored_box` |
| 计算内核 | `api/analyzers/` 共 11 个模块 | `api/hengpan/anchored_box.py` 单模块 |
| 数据来源 | **只支持 baostock 直连** | baostock（日线）/ **本地 `market.db`（60 分钟线）** |
| 判定口径 | 多窗口 × 多维度 AND（振幅 + 均线 + 波动率 + 量能 + 箱体质量 + 低位） | 末端锚定箱体 + 回验越界计数，支持多组规则一次算完 |
| 参数规模 | 30 余项（`index.py:44` `ScanConfigRequest`） | 6 项 × N 组规则 |

**关键差异**：横盘模块已经走通了「读本地库」这条路（`api/hengpan/scanner.py:205` 的 `use_local` 分支，子进程只读 SQLite、不建 baostock 连接），平台扫描还没有。加密扫描照抄这个分支即可。

---

## 3. 分层可复用性（实测逐列核对）

把 `api/analyzers/` 每个模块实际引用的 DataFrame 列全部提取出来核对：

| 模块 | 实际依赖的列 | 加密可用 |
|---|---|---|
| `price_analyzer.py` | close / high / low | ✅ |
| `volume_analyzer.py` | volume | ✅ |
| `box_detector.py` | close / high / low / volume | ✅ |
| `decline_analyzer.py` | high / low | ✅ |
| `position_analyzer.py` | close / high / date | ✅ |
| `enhanced_platform_analyzer.py` | 无（转发给上面几个） | ✅ |
| `technical_indicators.py` | close / high / low（算 MACD / RSI / KDJ / 布林） | ✅ |
| `breakthrough_analyzer.py` | close / volume + 上面算出的指标列 | ✅ |
| `window_weight_analyzer.py` | 无（只处理评分字典） | ✅ |
| `combined_analyzer.py` | 无（编排层） | ✅ |
| `fundamental_analyzer.py` | **peTTM / pbMRQ / pctChg** | ❌ 财报，加密无对应 |

**没有任何一处引用 `turn`（换手率）、`isST`、`amount` 或 `sh.`/`sz.` 代码前缀。** 窗口全部是 `df.iloc[-window:]` 按行数切片，与周期无关。

绑死 A 股的只有三处，全在编排层而非计算层：

| 位置 | 问题 | 处理 |
|---|---|---|
| `platform_scanner.py:263` | `executor.submit(fetch_kline_data, ...)` 直连 baostock，`initializer=baostock_login` | 抽成可注入的 loader |
| `platform_scanner.py:449` | `apply_industry_diversity_filter` 行业分散 | 用 `category` 顶替 `industry` |
| `platform_scanner.py:430` | `analyze_fundamentals` 基本面 | 加密强制关闭 |

`api/hengpan/anchored_box.py` 的复用性上级文档已确认，此处不重复。补充一点：它的 `extract_series`（第 31 行）对 `amount`/`turn` 做了 `if column in df else None` 容错，加密缺这两列不会报错，只是 `avg_amount`/`avg_turn` 为空——如需展示成交额，改成读 `quote_asset_volume` 即可。

---

## 4. 关键发现一：小时线上多维度筛选退化

这是本次调研最重要的发现，直接影响「两种模式都保留」的前提。

**样本**：创业板 250 只，本地 60 分钟线，窗口 80 根（对齐加密研究文档的回验根数），约 20 个交易日。

### 4.1 四项核心指标的实测分布

| 指标 | 含义 | 中位 | 10% | 25% | 75% | 90% |
|---|---|---|---|---|---|---|
| `box_range` | 窗口内 (最高−最低)/最低 | **0.1508** | 0.0919 | 0.1137 | 0.2091 | 0.2879 |
| `ma_diff` | MA5/10/20/30 末值的 std/mean | **0.0068** | 0.0031 | 0.0046 | 0.0097 | 0.0168 |
| `volatility` | 单根收益率标准差 | **0.0112** | 0.0072 | 0.0089 | 0.0144 | 0.0177 |
| `box_quality` | 箱体质量综合评分 | **0.9600** | 0.8400 | 0.9000 | 0.9900 | 0.9900 |

### 4.2 按 ScanView 当前默认参数逐层筛

`box_threshold=0.1` / `ma_diff_threshold=0.02` / `volatility_threshold=0.02` / `box_quality_threshold=0.8`：

```
全样本 250
  → box_range ≤ 0.10        41 只   ← 唯一真正起作用的闸门
  → + ma_diff ≤ 0.02        41 只   ← 一只没筛掉
  → + volatility ≤ 0.02     41 只   ← 一只没筛掉
  → + 箱体质量 ≥ 0.8        38 只   ← 只筛掉 3 只
```

**后三道闸门形同虚设。** 原因是日线的均线离散度和单根波动率，在小时线上天然缩小一个量级（中位 0.0068 / 0.0112 vs 阈值 0.02），A 股日线调出来的阈值在小时线上全部失效。

### 4.3 这意味着什么

平台扫描的「多维度 AND」优势在 1h 数据上被削成只看箱体振幅一项——而横盘模式本来就是单条件（末端锚定箱体 + 越界计数）。**两种模式的差异会被压缩。**

注意：这不是加密特有的问题，**现有的 A 股 60 分钟平台扫描已经处于这个状态**。想在加密上保留平台扫描的多维度价值，必须同时把 `ma_diff_threshold` 和 `volatility_threshold` 按周期重标定（见第 5 节），否则打开再多开关也不影响结果。

---

## 5. 关键发现二：参数必须按 category 分两套

### 5.1 换算基准

用第 4 节实测的 A 股 60 分钟线做锚，对齐上级研究文档 6.1 节的加密实测波动：

| | 80 根波动中位 | 相对 A 股 60m | 建议 `box_threshold` | `ma_diff_threshold` | `volatility_threshold` |
|---|---|---|---|---|---|
| A 股 60 分钟线 | 0.151 | 1.00× | 0.10（现默认） | 0.02 | 0.02 |
| **加密永续 1h** | 0.232 | **1.54×** | **≈ 0.15** | ≈ 0.010 | ≈ 0.017 |
| **TradFi 永续 1h** | 0.058 | **0.38×** | **≈ 0.04** | ≈ 0.003 | ≈ 0.004 |

> `ma_diff` 与 `volatility` 的建议值按波动倍数线性平移得出，属于起步值，需在真实加密数据上复测校准。`box_threshold` 有交叉验证（下节），可信度更高。

### 5.2 与横盘模式建议参数的交叉验证

上级研究文档 6.4 节从**横盘模式**的命中率实测给出的建议是：加密永续 15%、TradFi 4%~6%。

本次从**平台扫描**的波动分布独立推导得出：加密永续 ≈ 0.15、TradFi ≈ 0.04。

**两条独立路径结论一致**，这组箱高量级可以放心作为两个模式的共同起点。

### 5.3 为什么必须分开

上级研究文档已实测：1h 线 10% 箱高命中 113 个，其中 TradFi 占 101 个，加密只有 12 个。平台扫描同理——若不分开设参数，结果页翻几页全是黄金、美股，真正的加密横盘被埋在后面。

**实现上不需要跑两次扫描**：一次取数，对每个标的按其 `category` 取对应的那套阈值即可。

---

## 6. 关键发现三：低位判断的时间尺度失真

### 6.1 两个口径混用

`api/analyzers/decline_analyzer.py` 里存在两种时间口径：

| 位置 | 代码 | 实际口径 |
|---|---|---|
| 第 55 行 | `lookback_df = df.iloc[-lookback_days:]` | **按根数** |
| 第 91-92 行 | `days_between = (low_date - high_date).days` | **按真实日历天** |
| 第 37 行 | `if len(df) < 60` | **按根数**（硬编码最少 60 根） |
| 第 109-110 行 | `after_high_df.iloc[i:i+rapid_decline_days]` | **按根数** |

参数名全部叫 `_days`，但只有第 91 行是真的按天。

### 6.2 实测结果

39 只创业板股票，各取 150 根 60 分钟线，`decline_period_days=180`：

```
「高点→低点」实际跨越天数：中位 24 天，最大 45 天
decline_period_days=180 这一条：39/39 判定「满足」 —— 恒为真，约束完全失效
rapid_decline_days=30（实为 30 根 ≈ 7.5 个交易日）：15/39 判定急跌
```

### 6.3 换算到加密 1 小时线

加密 7×24 交易，每天 24 根（A 股 60 分钟线每交易日 4 根）：

| 参数 | 名义值 | A 股 60 分钟线实际 | 加密 1h 实际 |
|---|---|---|---|
| `high_point_lookback_days` | 365 | 91.2 个交易日 | **15.2 天** |
| `decline_period_days` | 180 | 45.0 个交易日 | **7.5 天**（约束恒为真） |
| `rapid_decline_days` | 30 | 7.5 个交易日 | **1.2 天** |
| 最少数据量 `len(df)<60` | 60 | 15.0 个交易日 | **2.5 天** |

想在加密上实现真正的「365 天回看」需要 8760 根，而本地库计划只保留 1500 根（62 天），**数据量根本不够**。

### 6.4 结论

加密平台扫描第一版**直接关掉低位判断**（`use_low_position=False`）。若后续要启用，两个选择：

1. 参数改名为显式的「根数」，前端标清「= N 根 K 线 ≈ M 天」；
2. 保留天数语义，把第 55 行的 `iloc` 切片改成按 `date` 列做真实时间窗过滤——但这要求本地保留足够长的历史。

---

## 7. 关键发现四：`box_detector` 的两处 A 股硬编码

### 7.1 箱高理想区间硬编码 3%~20%

`api/analyzers/box_detector.py:125-131`，占 `box_quality` 权重 15%：

```python
if 0.03 <= box_height_pct <= 0.2:
    height_factor = 1.0
elif box_height_pct < 0.03:
    height_factor = box_height_pct / 0.03
else:
    height_factor = max(0, 1 - (box_height_pct - 0.2) / 0.3)
```

不同箱高下的得分：

| 箱高 | height_factor | 备注 |
|---|---|---|
| 2% | 0.67 | 低波动 TradFi 会被打折 |
| 3%~20% | 1.00 | A 股日线常见区间 |
| **6%** | **1.00** | ← TradFi 永续 1h/80 根 波动中位，正好落在理想区 |
| **23%** | **0.90** | ← 加密永续 1h/80 根 波动中位，轻微打折，可接受 |
| 30% | 0.67 | |
| 40% | 0.33 | |
| ≥ 50% | **0.00** | 高波动币直接归零 |

加密永续中位数位置只打九折，不致命；但波动大的币会被系统性压分。**若加密扫描要用箱体质量这一关，建议把 3%~20% 改成按 category 传入的参数。**

### 7.2 `is_box_pattern` 硬编码 0.6 门槛

`box_detector.py:141`：

```python
is_box_pattern = box_quality >= 0.6   # 硬编码
```

而 `check_box_pattern`（第 293-298 行）同时要求 `is_box_pattern` 为 True **且** `box_quality >= box_quality_threshold`，所以把 `box_quality_threshold` 调到 0.6 以下不生效：

| 设定阈值 | 按参数本该通过 | 实际通过 |
|---|---|---|
| 0.3 | 248 只 | **244 只** |
| 0.4 | 248 只 | **244 只** |
| 0.5 | 246 只 | **244 只** |
| 0.6 | 244 只 | 244 只 |
| 0.7 | 240 只 | 240 只 |
| 0.8 | 232 只 | 232 只 |

实测影响很小（250 只里差 4 只），且这是**已存在的 A 股行为，不是加密引入的**。记录在案，不建议在加密改造中顺手改动——它会改变现有 A 股扫描结果。

---

## 8. 改造方案

### 8.1 设计原则

沿用项目里**已验证过的市场描述符模式**：`src/views/data/markets.js` 用 `ASHARE` / `CRYPTO` 两个配置对象，让一个 `LocalStorePanel.vue` 同时服务两个市场，界面一致、数据不混。扫描页照这个做，**不要复制一份 ScanView.vue**。

同时遵守「不破坏现有功能」：A 股平台扫描的默认行为、接口、参数一律不变。

### 8.2 后端改动

| 步骤 | 文件 | 改动 |
|---|---|---|
| 1 | `api/platform_scanner.py` | `scan_stocks` 增加可选的 `loader` 与 `initializer` 参数，默认仍是 `fetch_kline_data` + `baostock_login`，保持现有调用零影响；把 `submit()`（第 262-265 行）改为调用注入的 loader |
| 2 | `api/platform_scanner.py` | 后处理的基本面与行业分散两段（第 425-452 行）改为可跳过，加密传入跳过标记 |
| 3 | 新建 `api/crypto/platform_loader.py` | 子进程只读 `crypto.db` 的单标的读取函数，照 `api/hengpan/scanner.py:38` `fetch_local_kline` 写法；内部调 `crypto/reader.py` 的 `load_kline` |
| 4 | 新建 `api/crypto/platform_router.py` | `/api/crypto/platform/scan/start`、`/status/{id}`、`/cancel/{id}`、`/history`；复用 `api/task_manager.py` 和边扫边出（`append_streamed`）机制，照 `api/hengpan/router.py` 结构 |
| 5 | `api/index.py` | 注册新 router，与现有 `crypto_router` 同前缀风格 |

**币池不需要新写**：`api/crypto/db.py:232` `symbol_pool()` 已经现成，带 `min_quote_volume` 流动性过滤和 `status='TRADING'` 排除下架合约。

**扫描时点**：加密无「交易日」概念。用最新一根已完成 K 线的 `open_time` 作为扫描锚点（同步层已保证截掉未走完的末根）。

**数据缺口检查**：横盘模块的 `window_has_gap`（`hengpan/scanner.py:76`）基于交易日历判定停牌。加密无停牌，改成检查 `open_time` 步长是否恒为 3600000——用于识别新币上线不久或同步不全。

**字段映射**：

| 平台扫描期望 | 加密来源 |
|---|---|
| `code` | `symbol` |
| `name` | `baseAsset` |
| `industry` | `category` 的中文标签（加密永续 / TradFi 永续） |
| `date` | `reader.py` 已输出北京时间字符串，格式与 A 股分钟线一致 |
| `open/high/low/close/volume` | 同名，`reader.py` 已转 float |

### 8.3 前端改动

| 步骤 | 文件 | 改动 |
|---|---|---|
| 1 | 新建 `src/views/scan/scanMarkets.js` | 照 `views/data/markets.js` 写两个描述符：接口前缀、分组参数（`markets`→`categories`）、分组选项、字段取值器、文案（只/个、股票/交易对、行业/类别）、**两套默认参数** |
| 2 | `src/views/ScanView.vue` | 把 `BOARDS`（第 360 行）、`config.markets`、`industryOptions`、`stock.code/name/industry` 的直接引用换成从描述符读取；`use_fundamental_filter` 开关按描述符决定是否渲染 |
| 3 | `src/views/ScanView.vue` | 顶部加市场标签页（与 `DataView.vue` 的 tab 一致），或在 `App.vue` 新增 `/crypto-platform` 路由 |

前端对 A 股字段的耦合很浅——`stock.code` 6 处、`stock.name` / `stock.industry` 各 1 处、`BOARDS` 2 处，其余是中文文案。改造量小。

### 8.4 参数默认值（写进描述符）

| 参数 | A 股日线 | 加密永续 1h | TradFi 永续 1h |
|---|---|---|---|
| `windows` | `10,20,30` | `40,80,120` | `40,80,120` |
| `box_threshold` | 0.10 | **0.15** | **0.04** |
| `ma_diff_threshold` | 0.02 | 0.010 | 0.003 |
| `volatility_threshold` | 0.02 | 0.017 | 0.004 |
| `use_low_position` | true | **false** | **false** |
| `use_fundamental_filter` | false | **不可用** | **不可用** |
| `use_box_detection` | true | true（注意 7.1 的打折） | true |

窗口从 `10,20,30` 改成 `40,80,120` 的理由：加密 1h 线上 10 根 = 10 小时，作为「平台期」太短没有意义；40/80/120 根 ≈ 1.7/3.3/5 天，与横盘模块的 80 根回验对齐。

---

## 9. 两种模式在加密上的定位

用户明确要求两种模式都保留。在加密 1h 上，建议这样区分二者的职责，避免变成同一件事的两种写法：

| | 平台扫描 | 横盘选股 |
|---|---|---|
| 找什么 | **长期趋稳**：多个窗口同时成立的整理形态 | **当下的入场点**：末端 K 线正贴着箱体边界 |
| 判定特征 | 多窗口共振（40/80/120 根都通过）+ 量能缩量确认 | 末端锚定 + 回验越界计数，允许少量越界 |
| 箱体定法 | 全窗口取极值，箱体是「结果」 | 末端 K 线锚定，箱体是「假设」再回验 |
| 加密关键调整 | 窗口拉长；`ma_diff`/`volatility` 必须重标定（否则退化成单条件） | 用**振幅倍数模式**（上级文档已实证十字星对加密失效、对 TradFi 周末误报） |
| 适合的使用节奏 | 定期批量筛选候选池 | 盯盘时高频复扫 |

只要第 4 节的阈值重标定问题被解决，这个区分在加密上依然清晰，两个模式都值得保留。

---

## 10. 前置阻塞与待拍板项

### 10.1 阻塞

`api/data/crypto.db` 四张数据表**全部 0 行**：

```
crypto_symbol               0
crypto_ticker_24hr          0
crypto_kline_1h_perpetual   0
crypto_kline_1h_tradifi     0
```

建表已完成，同步一次未成功——本机出口 IP 在美国，Binance 返回 451（上级研究文档注意事项第 3 条）。**这个不解决，加密扫描写完也无法验证参数**，第 5 节的阈值只能停留在推算值。建议先把同步跑通。

### 10.2 待拍板

| 项 | 选项 | 建议 |
|---|---|---|
| 加密平台扫描入口位置 | ① 现有 `/platform` 页加市场标签页 ② 新增独立路由 | ①，与 `DataView` 的交互一致，用户不用记两个位置 |
| 两类资产参数如何呈现 | ① 界面上两套参数并列 ② 只显示当前勾选类别的那套 ③ 扫描时按标的 category 自动套用 | ③ + 界面上可展开查看/微调，一次扫描出全部结果 |
| TradFi 周末处理 | 上级文档三种方案 | 扫描时自动排除周末的 TradFi，与横盘模式保持同一策略 |
| `box_detector` 的 3%~20% 是否参数化 | ① 保持硬编码 ② 按 category 传入 | 加密第一版先观察实际影响，确认压分明显再改（改动会影响 A 股结果，需隔离） |
| `ma_diff`/`volatility` 的加密起步值 | 本文推算值 vs 真实数据复测 | 同步跑通后**必须复测**，推算值只作为占位 |

---

## 11. 复现脚本

本次调研用了两个只读探针，不写任何文件、不改任何代码。脚本本体是临时产物（`/tmp/probe_platform_hourly.py`、`/tmp/probe_decline_scale.py`，可能已被系统清理），核心代码原文附在下面，需用项目虚拟环境执行：

```bash
cd 2_a-share-platform-stocks-selection
api/.venv/bin/python <脚本路径>
```

### 11.1 核心指标分布与筛选漏斗（第 4、7 节）

```python
import sys, sqlite3
import numpy as np, pandas as pd

sys.path.insert(0, "<项目根目录>")
from api.analyzers.price_analyzer import calculate_price_features
from api.analyzers.box_detector import identify_support_resistance
from api.analyzers.volume_analyzer import calculate_volume_features

DB, WINDOW, SAMPLE = "api/data/market.db", 80, 250
conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

codes = [r[0] for r in conn.execute(
    "SELECT code FROM kline_60m_sz_gem GROUP BY code HAVING COUNT(*) >= ? "
    "ORDER BY code LIMIT ?", (WINDOW + 20, SAMPLE))]

rows = []
for code in codes:
    df = pd.read_sql_query(
        "SELECT date,open,high,low,close,volume FROM kline_60m_sz_gem "
        "WHERE code=? ORDER BY time DESC LIMIT ?", conn, params=(code, WINDOW + 20))
    df = df.iloc[::-1].reset_index(drop=True)
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    price = calculate_price_features(df, WINDOW)
    box = identify_support_resistance(df, WINDOW)
    rows.append({**price, "box_quality": box.get("box_quality", 0.0),
                 "is_box": bool(box.get("is_box_pattern"))})

data = pd.DataFrame(rows).replace([np.inf, -np.inf], np.nan)
# 逐层筛：验证 ma_diff / volatility / box_quality 在小时线上是否起作用
n1 = (data["box_range"] <= 0.10).sum()
n2 = ((data["box_range"] <= 0.10) & (data["ma_diff"] <= 0.02)).sum()
n3 = ((data["box_range"] <= 0.10) & (data["ma_diff"] <= 0.02) & (data["volatility"] <= 0.02)).sum()
print(len(data), "→", n1, "→", n2, "→", n3)
```

### 11.2 低位判断时间尺度（第 6 节）

```python
from api.analyzers.decline_analyzer import analyze_decline_speed

# 取 150 根 60 分钟线（本地库单只最多 176 根），用 decline_period_days=180 检验约束是否恒为真
res = analyze_decline_speed(df, lookback_days=150, decline_period_days=180,
                            decline_threshold=0.3, rapid_decline_days=30,
                            rapid_decline_threshold=0.15)
d = res["details"]
span = (pd.to_datetime(d["low_date"]) - pd.to_datetime(d["high_date"])).days
print(span, d["decline_period_satisfied"])   # 实测 39/39 恒为 True
```

---

## 附：与上级两份加密文档的分工

| 文档 | 负责范围 |
|---|---|
| 《加密货币横盘扫描数据源研究.md》 | 数据源、接口、字段映射、9 条注意事项、**横盘模式**的波动实测与参数建议 |
| 《加密永续本地存储方案-1小时线.md》 | 表结构、同步流程、读取层、查询性能、数据管理页 |
| **本文档** | **平台扫描模式**的复用性核对、小时线阈值退化、两模式职责划分、改造落点 |
