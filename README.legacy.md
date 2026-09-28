<div align="center">

# 📊 股票平台期扫描工具 📈

<img src="https://img.shields.io/badge/股票平台期-扫描工具-E6162D?style=for-the-badge">

[![License](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg?style=flat-square&logo=creativecommons)](https://creativecommons.org/licenses/by-nc-sa/4.0/)
[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Vue.js](https://img.shields.io/badge/Vue.js-3.x-4FC08D?style=flat-square&logo=vue.js&logoColor=white)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.95+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)

<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=12,15,20,24&height=200&section=header&text=平台期扫描工具&fontSize=80&fontAlignY=35&desc=基于箱体检测和均线分析的股票平台期识别系统&descAlignY=60&animation=fadeIn" />

</div>

**⚠️ 免责声明：本项目仅用于教育目的，不构成任何投资建议。投资有风险，交易需谨慎。**

<div align="center">
<img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/rainbow.png" width="100%">
</div>

## 项目概述

本项目是一个专注于股票平台期识别的扫描工具，能够通过技术分析方法自动识别处于平台期的股票，并提供可视化分析结果。

### 什么是平台期，为什么要做平台期检测？

**平台期**是指股票价格在一段时间内横向波动，形成相对稳定的上下边界（支撑位和阻力位）的时期。平台期通常代表了多空力量的暂时平衡，是市场决策的关键时期。

**平台期检测的重要性：**

<div align="center">
<table>
  <tr>
    <td align="center"><img src="https://img.icons8.com/fluency/48/null/stocks-growth.png" width="30px"/><br><b>突破信号</b></td>
    <td align="center"><img src="https://img.icons8.com/fluency/48/null/line-chart.png" width="30px"/><br><b>风险管理</b></td>
    <td align="center"><img src="https://img.icons8.com/fluency/48/null/economic-improvement.png" width="30px"/><br><b>趋势转变</b></td>
  </tr>
  <tr>
    <td>平台期突破往往预示着新趋势的开始</td>
    <td>平台期的边界可以作为设置止损或止盈的参考点</td>
    <td>平台期的形成和突破可能标志着市场趋势的变化</td>
  </tr>
</table>
</div>

本工具采用多维度分析方法，结合均线分析、波动率检测、箱体识别和成交量分析等技术，全面评估股票的平台期特征，为投资决策提供技术参考。

<div align="center">
<img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/rainbow.png" width="100%">
</div>

## 项目安装

### 依赖说明（重要）

`api/requirements.txt` **不能直接使用**，按它安装出的环境无法启动：

| 问题 | 说明 | 处理方式 |
| --- | --- | --- |
| `baostock<=0.8.9` | 0.8.9 连接的 `www.baostock.com:10030` 已停用，`bs.login()` 会一直阻塞 | 改装 `baostock>=0.9.4`（连接 `public-api.baostock.com:10030`） |
| 缺少 `colorama` | `index.py`、`data_fetcher.py`、`platform_scanner.py` 都导入它，但依赖树中没有任何包会带上它，启动即 `ImportError` | 手动安装 `colorama` |
| `pandas>=1.3.0` 无上限 | 会解析到 pandas 3.x，其 Copy-on-Write 与字符串 dtype 行为与本项目按 2.x 编写的代码不一致，不报错但结果可能有偏差 | 限制为 `pandas<3` |

> `python-dotenv` 已声明但项目未使用（原注释即标为 Optional），保留无影响。

### 后端安装与启动

推荐使用虚拟环境，避免与系统或 Homebrew 的 Python 冲突：

```bash
# 在项目根目录执行；Python 3.11 / 3.12 均可
python3 -m venv api/.venv

# 安装依赖，并修正上表中的三处问题
api/.venv/bin/python -m pip install -r api/requirements.txt
api/.venv/bin/python -m pip install colorama "pandas<3" "baostock>=0.9.4"

# 启动服务（在项目根目录执行）
api/.venv/bin/uvicorn api.index:app --host 127.0.0.1 --port 18001
```

后端启动后：

- 接口地址 `http://127.0.0.1:18001`
- 自动生成的接口文档 `http://127.0.0.1:18001/docs`

> **不建议加 `--reload`**，也不建议使用 `api/run.py`（其中写死了 `reload=True`）。未安装 `watchfiles` 时 uvicorn 会退回 StatReload，轮询 `api/.venv` 下的上万个文件，启动与响应都会明显变慢。

### 前端安装与启动

```bash
# 根目录下执行
npm install
npm run dev
```

## 页面说明

项目包含两个页面，均由 Vite 开发服务器提供（默认 `http://localhost:15173`）：

| 地址 | 说明 |
| --- | --- |
| `/` | 平台期扫描主界面 |
| `/data.html` | 数据管理：查看数据源状态、数据集字段含义，并按代码预览原始数据 |

主界面中的「案例管理」与「全屏图表」为覆盖层弹窗，不是独立页面（项目未引入 vue-router，地址栏不会变化）。

`vite.config.js` 已将两个页面都登记为构建入口；新增根目录 HTML 页面时需同步添加，否则 `npm run build` 会将其丢弃。

### 本地 60 分钟行情库

进入 `/#/data` 的「本地行情库」可选择板块并手动同步。沪市主板、深市主板和创业板默认选中，科创板需按数据权限自行选择。同步支持停止和断点续传；页面刷新后会恢复当前任务的进度显示。

60 分钟横盘扫描只读取 `api/data/market.db`，不会在扫描时访问 Baostock。日线扫描仍按现有方式实时联网。数据管理页还可按证券和日期查询、重新拉取或删除本地 K 线，并可预览清理、清空板块、压缩数据库和查看同步日志。

命令行可使用同一套存储层：

```bash
api/.venv/bin/python -m api.store.cli status
api/.venv/bin/python -m api.store.cli sync
```

完整的数据结构、复权规则与同步流程见 `docs/local-storage-v1-60m.md`。

## 常见问题

### 扫描失败：`Failed to query stock basics: 用户未登录`

Baostock 的会话绑定在 TCP 连接上。网络抖动导致连接中断后，服务端会对后续查询返回「用户未登录」。

`fetch_stock_basics()` 与 `fetch_industry_data()` 原本没有重试，一次网络抖动就会让整个扫描在第一步失败。现已补充与 `fetch_kline_data()` 一致的重试与重新登录逻辑（默认 3 次）。若 3 次后仍失败，通常说明网络到 Baostock 确实不通，可用数据管理页确认连通状态。

### Baostock 连接卡住无响应

Baostock 创建 socket 时未设置超时，服务器不可达时 `bs.login()` 会阻塞至操作系统放弃（约 75 秒）。若使用代理的 TUN 模式，本地可能先完成"假握手"，导致永久卡死。

处理方式：

- 使用规则模式，并添加 `DOMAIN-SUFFIX,baostock.com,DIRECT`
- Baostock 使用自有 TCP 协议（端口 10030），不走 HTTP，`HTTP_PROXY` 环境变量对其无效
- 打开 `/data.html`，其中的连通性探测只需几十毫秒即可判断服务器是否可达

### 扫描耗时

全市场扫描属于正常的长耗时操作：登录约 1–25 秒（取决于服务端负载），股票列表与行业分类各约 20 秒，随后逐只拉取日线（约 1 秒/只，默认 5 并发）。因此进度条会较长时间停留在 30% 以下。

## 数据来源

本项目使用 **Baostock** 作为数据源，在此对 Baostock 提供的优质数据服务表示诚挚的感谢。Baostock 提供了丰富的股票历史数据和基本面数据，为本项目的分析功能提供了坚实基础。

<div align="center">
<img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/rainbow.png" width="100%">
</div>

## 项目预览

<div align="center">
  <p><b>系统界面预览</b></p>
  <img src="img/UI.png" alt="系统界面" width="800"/>
  
  <p><b>分析结果展示</b></p>
  <img src="img/result.png" alt="分析结果" width="800"/>
</div>

<div align="center">
<img src="https://raw.githubusercontent.com/andreasbm/readme/master/assets/lines/rainbow.png" width="100%">
</div>

## 功能特点

<div align="center">
<table>
  <tr>
    <td align="center"><img src="https://img.icons8.com/fluency/48/null/line-chart.png" width="30px"/><br><b>多窗口分析</b></td>
    <td align="center"><img src="https://img.icons8.com/fluency/48/null/statistics.png" width="30px"/><br><b>箱体检测</b></td>
    <td align="center"><img src="https://img.icons8.com/fluency/48/null/economic-improvement.png" width="30px"/><br><b>低位分析</b></td>
  </tr>
  <tr>
    <td align="center"><img src="https://img.icons8.com/fluency/48/null/bonds.png" width="30px"/><br><b>突破预测</b></td>
    <td align="center"><img src="https://img.icons8.com/fluency/48/null/fine-print.png" width="30px"/><br><b>案例管理</b></td>
    <td align="center"><img src="https://img.icons8.com/fluency/48/null/stocks-growth.png" width="30px"/><br><b>可视化分析</b></td>
  </tr>
</table>
</div>

## 后端选股逻辑与参数设置说明

### 整体选股逻辑

股票平台期扫描工具使用多种过滤条件来识别处于平台期的股票。系统的核心逻辑如下：

1. **数据获取**：

   - 系统根据配置的窗口期自动计算回测时间范围
   - 结束日期默认为当前日期
   - 开始日期为当前日期减去最大窗口期的两倍天数
   - 使用 Baostock API 获取指定时间范围内的股票数据

2. **多重过滤机制**：

   - 系统采用"与"逻辑组合多个过滤条件
   - 股票必须通过所有启用的过滤条件才会被选中
   - 每个过滤条件都有独立的开关和参数设置

3. **主要过滤条件**：

   - **价格分析**：检查股票价格是否在指定窗口期内形成平台（振幅小、均线粘合、波动率低）
   - **成交量分析**：检查成交量是否在平台期内保持稳定
   - **低位分析**：检查股票是否从历史高点大幅下跌
   - **快速下跌分析**：检查股票是否经历过短期内的快速下跌
   - **箱体检测**：检查股票价格是否形成明显的支撑位和阻力位
   - **突破预测**：预测股票是否即将突破平台期
   - **窗口权重**：对不同窗口期的分析结果进行加权

4. **行业多样性**：
   - 系统默认启用行业多样性过滤
   - 确保选出的股票来自不同行业，避免行业集中风险

### 回测时间设置

在系统中，回测区间（日期范围）是通过以下方式设置和传递的：

1. **回测区间的自动计算**：

   ```python
   # 计算日期范围
   end_date = datetime.now().strftime('%Y-%m-%d')  # 使用当前日期作为结束日期
   # 使用最大窗口大小加上一些缓冲天数作为起始日期
   max_window = max(config.windows) if config.windows else 90
   start_date = (datetime.now() - timedelta(days=max_window * 2)).strftime('%Y-%m-%d')
   ```

2. **数据获取过程**：

   - 回测区间参数在数据获取阶段被使用
   - `fetch_kline_data`函数接收这些日期参数并从 Baostock API 获取数据

3. **分析过程**：

   - 获取到的数据（DataFrame）被传递给各个分析函数
   - 回测区间参数本身不会传递给分析函数
   - 各个分析函数使用相对参数（如 lookback_days, window 等）来处理数据

4. **各个过滤条件的数据处理方式**：
   - **低位分析**：使用`high_point_lookback_days`参数在 DataFrame 中查找高点
   - **快速下跌分析**：使用`lookback_days`和`rapid_decline_days`参数在 DataFrame 中分析下跌特征
   - **价格分析**：使用`window`参数获取最近的数据进行分析

### 快速下跌参数设置

快速下跌分析使用以下参数：

1. **lookback_days**：

   - 默认值为 365 天（查找历史高点的时间范围）
   - 前端界面没有提供填写框让用户修改这个参数
   - 这是一个固定参数，系统认为高点查找范围应该是一年

2. **decline_period_days**：

   - 默认值为 180 天（下跌应该发生的时间范围）
   - 前端界面同样没有提供修改选项

3. **rapid_decline_days**：

   - 默认值为 30 天（定义快速下跌的时间窗口）
   - 前端界面允许用户修改这个参数

4. **rapid_decline_threshold**：
   - 默认值为 0.15（15%，判定为快速下跌的最小下跌幅度）
   - 前端界面允许用户修改这个参数

### 窗口期设置

前端的窗口期设置（如"80,100,120"）用于以下几个方面：

1. **多窗口分析**：

   - 系统会使用这些窗口期分别进行平台期分析
   - 如果任何一个窗口期满足条件，则认为股票处于平台期

2. **为什么要填三组窗口**：

   - **多维度验证**：不同的窗口期可以从不同的时间尺度验证平台期特征
   - **灵敏度平衡**：短窗口期对近期变化更敏感，长窗口期更稳定
   - **互补性**：多个窗口期互相补充，提高识别准确性
   - **适应不同股票**：不同股票的平台期长度可能不同，多窗口可以适应这种差异

3. **窗口期的使用**：
   ```python
   for window in windows:
       # Price analysis
       price_analysis = analyze_price(
           df, window, box_threshold, ma_diff_threshold, volatility_threshold
       )
       # ...其他分析
   ```

### 箱体检测参数设置

箱体检测的参数设置如下：

1. **回测时间**：

   - 箱体检测没有专门的回测时间设置
   - 使用系统自动计算的回测时间范围
   - 与其他分析方法使用相同的时间范围，确保分析的一致性

2. **窗口期**：

   - 箱体检测使用最大窗口进行分析

   ```python
   # 使用最大窗口进行箱体检测，以获取更稳定的支撑位和阻力位
   max_window = max(windows) if windows else 90
   box_analysis = analyze_box_pattern(df, max_window)
   ```

3. **质量阈值**：
   - 前端界面允许用户设置箱体质量阈值
   - 用于判断箱体的清晰度和可靠性

### 低位分析与快速下跌分析的区别

1. **低位判断 (analyze_position)**：

   - **目的**：判断股票是否处于相对历史高点的低位
   - **主要参数**：
     - `high_point_lookback_days`：查找历史高点的时间范围（默认 365 天）
     - `decline_period_days`：下跌应该发生的时间范围（默认 180 天）
     - `decline_threshold`：判定为低位的最小下跌幅度（默认 0.3，即 30%）
   - **判断逻辑**：
     - 找出历史高点
     - 计算当前价格与历史高点的跌幅
     - 判断跌幅是否超过阈值且下跌发生在指定时间范围内

2. **快速下跌判断 (analyze_decline_speed)**：

   - **目的**：判断股票是否经历了快速下跌
   - **主要参数**：
     - `rapid_decline_days`：定义快速下跌的时间窗口（默认 30 天）
     - `rapid_decline_threshold`：判定为快速下跌的最小下跌幅度（默认 0.15，即 15%）
   - **判断逻辑**：
     - 在历史数据中寻找最大的快速下跌窗口
     - 计算该窗口内的下跌幅度
     - 判断下跌幅度是否超过阈值

3. **两者的区别**：

   - **时间范围不同**：低位判断关注较长时间范围，快速下跌判断关注较短时间窗口
   - **下跌幅度要求不同**：低位判断要求较大的下跌幅度，快速下跌判断要求较小的下跌幅度但要求在短时间内发生
   - **判断目的不同**：低位判断找出已经大幅下跌的股票，快速下跌判断找出经历过快速下跌的股票

4. **组合使用**：
   - 结合使用这两个条件，可以更精确地识别出符合特定模式的股票
   - 这种组合能够找出既处于低位又经历过快速下跌的股票

<div align="center">
<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=12,15,20,24&section=footer&height=100&animation=fadeIn" />
</div>

## 许可证
注意本项目非授权不可用于商业用途，如需授权请联系moonbridge24@gmail.com
