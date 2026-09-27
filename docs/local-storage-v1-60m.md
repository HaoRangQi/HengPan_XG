# 本地 K 线数据存储方案 · 第一版（60 分钟线）

> 范围：只做 60 分钟线的本地化存储。日线、周线、5/15/30 分钟线放到后续版本。
> 目标：扫描和分析全部改读本地，不再每次联网，避免 baostock 封禁。

**字段原则：表结构严格按 Baostock 文档的字段名和字段数落库，不改名、不合并、不裁剪。**
格式转换（时间格式化、类型转换、复权、停牌过滤）全部放在读取层，存储层只负责原样保存。

---

## 1. 为什么要存本地

现在每次横盘扫描都会用多进程逐只联网拉 K 线，一次约 5000 次请求。baostock 对 IP 有封禁策略（公开统计接口 `/helpdocs/api/wd-blacklist-stats` 可查），触发后封禁 6 小时起，且封禁时长按年内被封次数递增。扫十来次参数就可能超限。

改成本地存储后：

```
baostock ──(数据管理页点「同步」)──▶ api/data/market.db
                                         │
                       横盘扫描 / 板块分析 ◀─┘   只读本地，不联网
```

- **同步**：手动触发，增量拉取，中断后重新点会从断点继续。
- **扫描**：只读本地，0 次网络请求，可以反复调参数。

---

## 2. 数据来源与字段

### 2.1 K 线接口

```python
bs.query_history_k_data_plus(
    code,                                                    # sh.600000
    "date,time,code,open,high,low,close,volume,amount,adjustflag",
    start_date, end_date,
    frequency="60",                                          # 60 分钟线
    adjustflag="3",                                          # 不复权
)
```

60 分钟线**没有**按日期批量取全市场的接口，只能逐只请求。单次耗时 0.2–1.4 秒。

### 2.2 分钟线字段（文档原文，共 10 个）

适用 5、15、30、60 分钟线，**不包含指数**。

| 参数名称 | 参数描述 | 说明 |
|---|---|---|
| date | 交易所行情日期 | 格式：YYYY-MM-DD |
| time | 交易所行情时间 | 格式：YYYYMMDDHHMMSSsss |
| code | 证券代码 | 格式：sh.600000。sh：上海，sz：深圳 |
| open | 开盘价格 | 精度：小数点后 4 位；单位：人民币元 |
| high | 最高价 | 精度：小数点后 4 位；单位：人民币元 |
| low | 最低价 | 精度：小数点后 4 位；单位：人民币元 |
| close | 收盘价 | 精度：小数点后 4 位；单位：人民币元 |
| volume | 成交数量 | 单位：股；时间范围内的累计成交数量 |
| amount | 成交金额 | 精度：小数点后 4 位；单位：人民币元；时间范围内的累计成交金额 |
| adjustflag | 复权状态 | 不复权、前复权、后复权 |

**这 10 个字段全部入库**，一个不少、一个不改。

分钟线字段集的局限（第一版接受，第二版做日线时解决）：

- 没有 turn（换手率）、tradestatus（停牌）、isST、pctChg、preclose —— 这些只有日线才有。
- 不包含指数，所以扫描日不能靠上证指数的分钟线确定，要用股票样本。

每只股票每个交易日 4 根：10:30、11:30、14:00、15:00（time 字段形如 `20260924150000000`）。

### 2.3 其它接口字段（同样原样入库）

| 接口 | 字段 |
|---|---|
| `query_stock_basic()` | code, code_name, ipoDate, outDate, type, status |
| `query_stock_industry()` | updateDate, code, code_name, industry, industryClassification |
| `query_adjust_factor()` / `query_daily_adjust_factor()` | code, dividOperateDate, foreAdjustFactor, backAdjustFactor, adjustFactor |
| `query_trade_dates()` | calendar_date, is_trading_day |

---

## 3. 表结构

数据库文件：`api/data/market.db`（SQLite，开 WAL 模式）。
`.gitignore` 需要加 `api/data/*.db*`。

所有来自接口的列一律沿用接口原名（含大小写，如 `code_name`、`ipoDate`、`backAdjustFactor`）。
少数本地派生列用于分区和记账，在下面明确标注 `-- 本地`。

### 3.1 K 线表：按板块拆分

板块 key 沿用 `api/platform_scanner.py:25` 的 `BOARD_PREFIXES`，全项目只有这一套板块命名。

| 板块 | key | 表名 | 股票数 |
|---|---|---|---|
| 沪市主板 | `sh_main` | `kline_60m_sh_main` | 1702 |
| 深市主板 | `sz_main` | `kline_60m_sz_main` | 1494 |
| 创业板 | `sz_gem` | `kline_60m_sz_gem` | 1408 |
| 科创板 | `sh_star` | `kline_60m_sh_star` | 618 |

科创板建表，但同步时默认不勾选，由用户按自己是否有权限决定。
北交所 baostock 不支持，不建表。

四张表结构完全相同，10 列与接口字段一一对应：

```sql
CREATE TABLE kline_60m_sz_gem (
  date       TEXT NOT NULL,   -- YYYY-MM-DD
  time       TEXT NOT NULL,   -- YYYYMMDDHHMMSSsss
  code       TEXT NOT NULL,   -- sh.600000
  open       TEXT,            -- 人民币元，4 位小数
  high       TEXT,
  low        TEXT,
  close      TEXT,
  volume     TEXT,            -- 股
  amount     TEXT,            -- 人民币元，4 位小数
  adjustflag TEXT,            -- 本地统一为 '3' 不复权
  PRIMARY KEY (code, time)
) WITHOUT ROWID;
```

**为什么价格列用 TEXT**：Baostock 返回的就是字符串，原样存不丢精度、不引入浮点误差，也不会把空串变成 0。类型转换在读取层用 `pd.to_numeric` 做，和现有 `clean_kline()` 的处理一致。
如果后续实测确认全部为规范数值且无空值，再考虑改 REAL —— 第一版不提前优化。

**主键 (code, time)**：`time` 已含日期，全局唯一；`date` 冗余但是文档字段，照存。
`WITHOUT ROWID` + 该主键使同一只股票的数据物理连续存放，单只查询走主键。

另建一个跨板块视图，供扫全市场用：

```sql
CREATE VIEW kline_60m_all AS
  SELECT 'sh_main' AS board, * FROM kline_60m_sh_main
  UNION ALL SELECT 'sz_main', * FROM kline_60m_sz_main
  UNION ALL SELECT 'sz_gem',  * FROM kline_60m_sz_gem
  UNION ALL SELECT 'sh_star', * FROM kline_60m_sh_star;
```

### 3.2 证券基本资料

```sql
CREATE TABLE stock_basic (
  code       TEXT PRIMARY KEY,
  code_name  TEXT,
  ipoDate    TEXT,
  outDate    TEXT,            -- 退市日期，未退市为空
  type       TEXT,            -- 1 股票 / 2 指数 / 3 其它 / 4 可转债 / 5 ETF
  status     TEXT,            -- 1 上市 / 0 退市
  board      TEXT NOT NULL,   -- 本地：sh_main / sz_main / sz_gem / sh_star
  updated_at TEXT             -- 本地：最后同步时间
);
```

只写入 `type='1'`（股票，排除指数、ETF、可转债），但 `type` 列照存以备核对。
退市股票（`status='0'`）保留，K 线数据也不删。
`board` 在写入时用 `BOARD_PREFIXES` 判断一次，之后全部直接读这一列。

> 顺带修一个现有缺陷：`BOARD_PREFIXES['sz_gem']` 漏了 `sz.302`，中航成飞（sz.302132）目前扫不到。

### 3.3 行业分类

`query_stock_industry()` 是独立接口，字段与 `query_stock_basic()` 不同，单独建表，不与 stock_basic 合并。

```sql
CREATE TABLE stock_industry (
  code                   TEXT PRIMARY KEY,
  code_name              TEXT,
  industry               TEXT,   -- 可能为空串
  industryClassification TEXT,   -- 实测当前为「证监会行业分类」
  updateDate             TEXT
);
```

官方每周一更新。读取时与 stock_basic 按 code 关联。

### 3.4 复权因子

```sql
CREATE TABLE adjust_factor (
  code             TEXT NOT NULL,
  dividOperateDate TEXT NOT NULL,   -- 除权除息日期
  foreAdjustFactor TEXT,            -- 向前复权因子（见下方警告）
  backAdjustFactor TEXT,            -- 向后复权因子
  adjustFactor     TEXT,            -- 本次复权因子
  PRIMARY KEY (code, dividOperateDate)
) WITHOUT ROWID;
```

首次完整复权因子同步另用本地表 `adjust_factor_sync(code, completed_at)` 记录每只证券的完成状态。
这张表不对应 Baostock 字段，只用于中断后从未完成证券继续，避免重新发出数千次请求。

三个因子列都按文档存下来，但**读取层只用 `backAdjustFactor`**，原因见下。

> **重要：`foreAdjustFactor` 不能直接用于计算前复权。**
> 它是相对「查询时最近一次除权」的相对值，最新一条恒为 1.0。每发生一次新的除权，该股票所有历史行的 `foreAdjustFactor` 都会整体变化。
> 实测 sh.600000：全量查询时四行的 fore 依次为 0.893976 / 0.926782 / 0.954887 / 1.000000；而用 `query_daily_adjust_factor(date)` 按日增量取到的行，fore 恒为 1.000000 —— 两种取法存下来的值互相矛盾。
> `backAdjustFactor` 是累计值，不随后续除权变化，可以安全地增量累积。前复权用 back 换算（见 5.3）。

### 3.5 交易日历

```sql
CREATE TABLE trade_calendar (
  calendar_date  TEXT PRIMARY KEY,   -- YYYY-MM-DD
  is_trading_day TEXT NOT NULL       -- 1 交易日 / 0 非交易日
);
```

用来判断「今天该不该有数据」，区分「非交易日」和「数据源还没更新」。

### 3.6 同步日志（纯本地表，无接口对应）

```sql
CREATE TABLE sync_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  action      TEXT,      -- sync / cleanup / refetch / vacuum
  boards      TEXT,      -- 逗号分隔的板块 key
  started_at  TEXT,
  finished_at TEXT,
  status      TEXT,      -- running / completed / failed / cancelled
  requests    INTEGER,   -- 本次发出的请求数，用于监控封禁风险
  rows        INTEGER,   -- 写入行数
  failed      INTEGER,   -- 失败股票数
  message     TEXT
);
```

### 3.7 实测体积与查询速度

按上面的真实表结构灌入三大板块 4604 只 × 42 个交易日 × 4 根 = 773,472 行：

| 指标 | 实测 |
|---|---|
| 文件大小 | 78 MB |
| 批量写入 | 2.9 秒 |
| 单只查最近 1 个月（72 行） | < 1 ms |
| 单板块查最近 1 个月（33 万行） | 708 ms |
| 查每只股票的最新 time（4604 只） | 253 ms |

含科创板约 88 万行、90 MB。体积完全不是问题。

---

## 4. 同步流程

### 4.1 步骤与请求数

| 步骤 | 接口 | 请求数 | 频率 |
|---|---|---|---|
| 1. 交易日历 | `query_trade_dates` | 1 | 跨年或首次 |
| 2. 证券基本资料 | `query_stock_basic` | 1 | 距上次超过 7 天 |
| 3. 行业分类 | `query_stock_industry` | 1 | 距上次超过 7 天 |
| 4. 复权因子 | `query_daily_adjust_factor` 按交易日 | 每个新交易日 1 次 | 每次同步 |
| 5. 60 分钟线 | `query_history_k_data_plus` 逐只 | 每只 1 次 | 每次同步 |

三大板块一次同步约 4600 次请求，远低于封禁阈值。

首次初始化时复权因子改用 `query_adjust_factor(code)` 逐只拉全量历史（约 4600 次），之后才转按日增量。

### 4.2 增量规则

对每只股票：

```
本地最后一根 time  →  start_date = 该 time 对应的日期   （当天可能只存了一半，重拉覆盖）
本地没有数据       →  start_date = 今天 - 保留天数
end_date          →  交易日历上最近的交易日
```

主键冲突时 `ON CONFLICT(code, time) DO UPDATE`，重复拉取只覆盖，不产生重复行。

失败的股票不用单独记录：它本地的最后一根还停在旧时间点，下次同步会自动补上。

### 4.3 并发与限速

沿用现有扫描器的写法（`api/hengpan/scanner.py` 的 `_init_worker`）：

- `ProcessPoolExecutor`，默认 3 个进程（比扫描的 5 个保守，降低封禁风险）。
- 每个子进程先 `socket.setdefaulttimeout(30)` 再 `baostock_login()`。
- **写库只在主进程做**，子进程只负责取数返回。SQLite 同一时刻只能有一个写入者。
- 累积 200 只股票的数据批量写一次，写完更新进度。
- 取数结果不做任何清洗，`rs.get_row_data()` 的字符串原样入库。

> Baostock 自带的 `rs.get_data()` 在 pandas 2 下遇到多页结果会报 `df.append` 错误，必须用 `while rs.next()` 逐行读。现有代码已是这个写法。

### 4.4 数据源未更新的判断

调用返回空数据时，分两种情况：

- 交易日历显示 `end_date` 是交易日，但连续多只股票都返回空 → 数据源当天还没入库，停止同步并提示，不计为失败。
- `end_date` 不是交易日 → 正常，跳过。

### 4.5 进度与取消

复用现有的 `task_manager`（`api/task_manager.py`），和横盘扫描一样返回 `task_id`，前端轮询进度、可随时取消。
服务端同一时间只接受一个本地同步任务；取消会在各元数据阶段之间检查，并强制回收仍在运行的进程池工作进程。
按日复权因子通过 `store_meta.adjust_factor_daily_through` 记录已经同步到的交易日，空结果也会推进游标。

---

## 5. 读取与复权

### 5.1 为什么要复权

除权当天不复权价格会出现缺口。实测 sh.600000 在 2026-07-16 除权，前一日收盘 9.31，除权后 8.89，**缺口 4.5%**。横盘箱体规则本身就是 4% 这个量级，一个缺口足以造成假突破或把箱体切断。除权并不罕见：单日就有 43 只（07-16）、50 只（09-24），5–7 月分红季更密集。

### 5.2 为什么存不复权而不是直接存前复权

前复权价格**每次除权都会导致该股票全部历史价格改变**，已存的数据就作废了，增量更新的前提不成立。

存不复权 + 复权因子：原始数据写进去永远不用改，读取时现算。代价只是每天多 1 次请求取复权因子，以及读取时一步乘法。

### 5.3 换算公式

```
后复权价 = 不复权价 × backAdjustFactor(当天)
前复权价 = 不复权价 × backAdjustFactor(当天) ÷ backAdjustFactor(最新)
```

`backAdjustFactor(当天)` 取该股票 `dividOperateDate <= 当天` 的最后一条，用 `pandas.merge_asof` 实现。没有除权记录的股票因子按 1 算。

已实测：这样算出的结果与 baostock 服务端 `adjustflag=1/2` 返回的数据完全一致，60 分钟线同样适用。
（校验：sh.600000 在 2026-07-10 的 back 为 12.763991，最新为 13.367013，比值 0.954887，正好等于全量查询时该行的 foreAdjustFactor。）

> 待验证：送转股时 baostock 是否同时调整 volume。第一版按「只调价格，不调量」实现，验证后如有出入再修正。
> （2026-09-27 本机 IP 被封至 15:15，未能测完。）

### 5.4 对外接口

存储层只暴露一个读取函数：

```python
load_kline_60m(boards, start, end, adjust="qfq", codes=None) -> DataFrame
```

职责分工：

- **存储层**：原样保存接口字符串，不做任何加工。
- **读取层**：类型转换 → 复权换算 → 时间格式化，输出与现有 `clean_kline()` 完全一致的 DataFrame（`date` 列为 `YYYY-MM-DD HH:MM:SS`，价格列为 float），扫描逻辑一行不用改。

参数 `adjust`：`qfq` 前复权（默认）/ `hfq` 后复权 / `raw` 不复权。

### 5.5 查询模式与实测性能

以下数字均在真实表结构上实测：773,472 行（4604 只 × 42 个交易日 × 4 根），macOS + SQLite WAL。

#### 场景一：某只股票的最新 100 根（看图、单只诊断）

```sql
SELECT * FROM kline_60m_sz_gem
 WHERE code = ?
 ORDER BY time DESC
 LIMIT 100;
```

**0.09 毫秒**。执行计划：

```
SEARCH kline_60m_sz_gem USING PRIMARY KEY (code=?)
```

主键 `(code, time)` + `WITHOUT ROWID` 让同一只股票的行按 `time` 有序、物理连续存放。`ORDER BY time DESC LIMIT 100` 是从该股票区间的**末尾向前走 100 步**就停 —— 不扫全表、不排序、不建临时 B 树。取 100 根和取 10000 根的成本只差在走多少步。

结果是倒序，读取层 `[::-1]` 反转即可；不要在 SQL 里再套一层 `ORDER BY time ASC`，那会引入一次排序。

同一只股票无论在表头、表中、表尾，耗时都是 0.09–0.21 毫秒，没有位置差异。

#### 场景二：整个板块每只取最新 100 根（扫描用）

先按交易日历把「100 根」换算成日期界限（100 根 ≈ 25 个交易日，取 30 天留余量），再交给 pandas 按 code 分组取尾部：

```sql
SELECT code, time, open, high, low, close
  FROM kline_60m_sz_gem
 WHERE code >= 'sz.30' AND code < 'sz.31'
   AND time >= ?;
```

```python
df.groupby("code", sort=False).tail(100)
```

单板块（创业板 1408 只）**586 毫秒**；逐只循环 1408 次是 437 毫秒，两者同一量级，选可读性更好的写法即可。

三大板块全市场每只最新 100 根，三种写法实测：

| 写法 | 耗时 |
|---|---|
| 逐只 `code=? AND time>=?` 循环 4604 次 | 1471 ms |
| 一次 `time>=cutoff` 扫描 + pandas tail | 1812 ms |
| 逐只 `ORDER BY time DESC LIMIT 100` 循环 | 1917 ms |
| 窗口函数 `ROW_NUMBER() OVER (PARTITION BY code)` | 3526 ms |

前三种都在 1.5–2 秒，差别不大；**窗口函数明显最慢，不要用**。

#### 场景三：某只股票在指定日期区间内是否横盘

`date` 一天重复 4 行，单独无法区分。但主键第二列是 `time`（`YYYYMMDDHHMMSSsss`），**它本身就是「日期 + 时分秒」**，即所谓「第三个区分字段」已经包含在内。`(code, time)` 就是完整的三元组。

`time` 定长、字典序等于时间序，日期区间用前缀范围表达即可：

```sql
-- 2026-08-10 ~ 2026-09-10
SELECT * FROM kline_60m_sz_gem
 WHERE code = ?
   AND time >= '202608100000000000'
   AND time <= '202609109999999999';
```

**0.09 毫秒**，执行计划：

```
SEARCH kline_60m_sz_gem USING PRIMARY KEY (code=? AND time>? AND time<?)
```

B 树里就是一段连续区间，定位起点顺着读到终点，不需要任何额外索引。

| 范围 | 耗时 |
|---|---|
| 单只 + 日期区间 | 0.09 ms |
| 创业板 1408 只 + 日期区间 | 264 ms |
| 全市场 4604 只 + 日期区间 | 990 ms |

两个提醒：

- 单只查询直接写 `date BETWEEN ? AND ?` 也是 0.09 ms —— SQLite 先用 `code=?` 把范围缩到该股票的 168 行，再在其中过滤 `date`。**但这只在带 `code` 时成立**，批量查询这么写会退化成全表扫描。读取层统一用 `time` 前缀。
- 实测建 `(code, date, time)` 联合索引：`date BETWEEN` 反而从 0.09 ms 变慢到 0.29 ms（非覆盖索引还要回表），文件从 86 MB 涨到 153 MB（**+78%**）。纯亏。

#### 两条性能纪律

**1. 不要给 `time` 加索引。**
实测加了 `time` 索引后，全市场取数从 1812 ms 变慢到 3527 ms，文件还多占 33 MB。原因：批量取数要读的是表里 40%–60% 的行，顺序扫描比「走索引再回表随机取行」快得多。单只查询走主键即可，本来就不需要 `time` 索引。

**2. 只 SELECT 需要的列。**
全表 10 列 2564 ms，只取分析用的 6 列（code, time, open, high, low, close）1551 ms —— **省掉 40%**。`load_kline_60m()` 应支持按需指定列，箱体分析用不到 amount 和 adjustflag 时就不要查出来。

#### 关于 `date` 索引：第一版不加

`date` 与 `time` 冗余（`time` 前 8 位即日期），因此只有「不带 code、纯按日期过滤」的查询才可能用上 `date` 索引。这类查询全部来自数据管理页，实测如下：

| 场景 | 无索引 | 有索引 |
|---|---|---|
| 某天全市场有多少只股票 | 84 ms | 3 ms |
| 某天全市场快照 | 107 ms | 45 ms |
| 按天统计行数 `GROUP BY date` | 533 ms | 89 ms |
| 本地数据起止日期 `MIN/MAX(date)` | 130 ms | 107 ms |
| **清理过期数据 `DELETE WHERE date<?`** | **620 ms** | **1146 ms** |

代价：

| 指标 | 无索引 | 有索引 |
|---|---|---|
| 文件大小 | 86 MB | 123 MB（**+43%**） |
| 同步批量写入 | 2.7 s | 4.2 s（**+55%**） |
| 清理删除 | 620 ms | 1146 ms（**+85%**） |

结论：**不加**。受益的都是数据管理页上偶尔点一次的统计，0.1–0.5 秒完全无感；代价却是天天都要付的 —— 磁盘多 43%、每次同步写入慢 55%、清理反而慢 85%（因为删行时要同步维护索引）。

**扫描日不要用 `SELECT MAX(date) FROM 大表`**（87 ms，走的是主键全扫）。两个更好的办法：

```sql
-- 用任一只长期正常交易的股票探测，走主键，0 ms
SELECT MAX(time) FROM kline_60m_sh_main WHERE code = 'sh.600000';
```

或直接从 `sync_log` 读上次同步记录的数据截止时间，零查询。

索引是纯物理结构，任何时候都能 `CREATE INDEX` / `DROP INDEX`，不影响数据。等数据管理页真做出来、某个统计确实慢到有感，再加也来得及。

#### 小结

| 需求 | 写法 | 实测 |
|---|---|---|
| 单只最新 N 根 | `WHERE code=? ORDER BY time DESC LIMIT N` | 0.09 ms |
| 单只指定区间 | `WHERE code=? AND time BETWEEN ? AND ?` | 0.09 ms |
| 单板块每只最新 N 根 | 前缀范围 + `time>=cutoff` + `groupby.tail(N)` | 0.6 s |
| 全市场每只最新 N 根 | 逐板块执行上一条 | 1.5–2 s |

当前主键设计对这四种场景都是最优的，第一版不建任何额外索引。

索引是纯物理结构，`CREATE INDEX` / `DROP INDEX` 随时可执行，不动数据、不改表结构。以后如果数据管理页的日期统计确实慢到有感，再给 `time` 或 `date` 加索引即可 —— 但要记得代价：文件涨 40%–80%、同步写入慢 55%、清理删除慢 85%。

---

## 6. 横盘扫描改读本地

`api/hengpan/` 需要改三处：

| 位置 | 现在 | 改为 |
|---|---|---|
| 股票池 | `fetch_stock_basics()` + `fetch_industry_data()` 联网，40–80 秒 | 读 `stock_basic` 关联 `stock_industry`，毫秒级 |
| 扫描日 | `resolve_scan_date()` 抽样 8 只股票联网探测 | 取所选板块本地数据的最新 `time` |
| K 线 | 进程池逐只联网拉取 | 每个板块一次 `load_kline_60m()` |

逐只分析的循环（`analyze_stock`）不动。

**注意保留时长和回验根数的冲突**：保留 2 个月约 160 根 K 线，而规则的 `lookback` 上限是 250（`api/hengpan/router.py:39`）。超过本地根数的规则会因数据不足被跳过，计入「有效 K 线不足」。扫描页和清理按钮旁都要显示「当前本地约 N 根」。

本地数据落后于交易日历最新交易日时，扫描照跑，但提示「本地数据截至 X，建议先同步」。

---

## 7. 数据管理页

在现有 `#/data` 页（`src/views/DataView.vue`）新增「本地数据」区块。

| 操作 | 功能 |
|---|---|
| 查 | 各板块行数、股票数、起止时间、最后同步时间、数据库文件大小；按代码/板块/时间查看 K 线，可切换前复权、后复权、不复权 |
| 增/改 | 同步按钮：勾选板块（科创板默认不勾）、进度条、取消；单只股票指定时间段「重新拉取」并覆盖 |
| 删 | 清理过期数据：默认保留 60 天，先预览会删多少行，确认后执行；清空某板块；删除某只股票或某时间段；压缩数据库（`VACUUM`）回收空间 |
| 日志 | `sync_log` 最近记录，含每次请求数 |

后端路由放在 `/api/store/`：

```
GET    /api/store/overview           概览
POST   /api/store/sync               启动同步 → task_id
GET    /api/store/sync/status/{id}   进度
POST   /api/store/sync/cancel/{id}   取消
POST   /api/store/cleanup            清理（dry_run 参数先预览）
GET    /api/store/kline              查看 K 线
DELETE /api/store/kline              删除
POST   /api/store/refetch            单只重拉
POST   /api/store/vacuum             压缩
GET    /api/store/log                同步日志
```

---

## 8. 代码组织

新建 `api/store/`，写法参照现有的 `api/hengpan/`：

```
api/store/
  __init__.py
  db.py        建连接（WAL）、建表、板块 → 表名映射
  sync.py      同步任务：基本资料、行业、交易日历、复权因子、60 分钟线增量
  reader.py    load_kline_60m()、复权换算、格式化
  router.py    /api/store/* 接口
  tests/       pytest，与现有测试同风格
```

前端新建 `src/store/`，挂进 `DataView.vue`。

---

## 9. 实施顺序

每一步单独可跑、可验证。

| 阶段 | 内容 | 验收 |
|---|---|---|
| 1 | `db.py` + `sync.py` + 命令行入口 | 三大板块同步成功；请求数、行数符合预期；库里字段与接口逐列一致 |
| 2 | `reader.py` | 本地算出的前复权与 baostock `adjustflag=2` 逐根一致 |
| 3 | 横盘扫描改读本地 | 同一扫描日，新旧两种方式结果一致 |
| 4 | `router.py` + 数据管理页 | 同步、清理、查看均可用 |

---

## 10. 后续版本

| 版本 | 内容 |
|---|---|
| v2 | 日线（保留 200 根，用 `query_daily_history_k_AStock` 按日批量，每天 1 次请求）。日线字段是另一套 18 列（含 preclose、turn、tradestatus、pctChg、isST、peTTM、pbMRQ、psTTM、pcfNcfTTM），同样原样建表，不与分钟线表混用 |
| v3 | 5 / 15 / 30 分钟线，字段与 60 分钟线相同，表名 `kline_{周期}_{板块}`，同步时按需勾选周期 |
| v4 | 45 分钟线（接口不提供，用 15 分钟线合成）；周线、月线（字段是第三套 11 列，且接口只在周末/月末才给当期数据，周中需用日线合成）；定时自动同步 |

合成的可行性已验证：15 分钟线合成 30、60 分钟线，5 分钟线合成 15 分钟线，OHLC 完全一致，成交量最多差 1 手。

**45 分钟线待定**：A 股上下午各 120 分钟，不能被 45 整除。按上下午分段切则每半天为「45+45+30」，最后一根不足周期。是否需要、如何切分待定。

---

## 11. 已知风险

| 风险 | 说明 | 对策 |
|---|---|---|
| IP 封禁 | 2026-09-27 09:10 本机被封 6 小时，封禁记录计数仅 6。当时走 Clash TUN，出口是 AWS 东京节点（18.183.84.253），可能有他人共用，原因未确认 | Clash 给 `baostock.com` 加 DIRECT 规则；同步日志记录每次请求数 |
| 数据源延迟 | baostock 每日入库时间文档未说明 | 交易日返回空数据时提示「数据源尚未更新」，不计失败 |
| foreAdjustFactor 语义 | 相对值，会随新除权整体变化，两种取法结果矛盾 | 读取层只用 backAdjustFactor 换算（见 3.4） |
| 送转股是否调量 | 未验证 | 第一版只调价格，验证后修正 |
| 保留期 < 回验根数 | 2 个月约 160 根，规则 `lookback` 上限 250 | 页面显示当前本地根数 |
