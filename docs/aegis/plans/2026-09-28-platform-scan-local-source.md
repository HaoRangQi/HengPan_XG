# 平台期扫描本地数据源实施计划

## Goal

让 `#/platform` 默认从本地 SQLite 行情库执行平台期扫描，扫描期间不访问 Baostock；同时保留旧版联网扫描用于结果比对。

## Architecture

- `api/platform_scan_source.py` 作为平台扫描数据源选择的唯一 owner：本地模式读取 `stock_basic`、`stock_industry` 和本地最新交易日；旧版模式保留现有 Baostock 股票池与行业读取。
- `api/platform_scanner.py` 继续作为平台分析算法 owner，只新增可选的本地 K 线读取入口；两种来源共用同一分析、进度、取消和结果结构。
- `/api/scan/start` 增加 `data_source` 请求字段。缺省值保持 `baostock`，以兼容旧页面和旧客户端；`ScanView.vue` 显式提交 `local`。
- `src/views/platformScanSource.js` 负责前端来源切换规则：默认本地 60 分钟，旧版联网可选日线或 60 分钟。

## Tech Stack

- FastAPI + Pydantic + pandas + SQLite + Baostock
- Vue 3 + Axios + Vite
- Python `unittest` 与 Node.js `node:test`

## Baseline/Authority Refs

- `docs/local-storage-v1-60m.md`：本地行情库与离线扫描约束
- `api/store/db.py`、`api/store/reader.py`：本地股票池和 60 分钟 K 线 owner
- `api/index.py`：平台扫描异步任务和兼容 API
- `api/platform_scanner.py`：平台算法和逐股执行
- `src/views/ScanView.vue`、`src/views/LegacyScanView.vue`：新版与旧版页面

## Compatibility Boundary

- 未传 `data_source` 的 `/api/scan/start` 请求继续使用 Baostock。
- `#/legacy` 和同步 `/api/scan` 的既有联网行为不变。
- 本地模式只支持 60 分钟 K 线；不静默回退联网，也不允许会联网的基本面筛选。
- 两种来源共用原有任务状态、取消、流式结果和历史详情格式。

## Verification

- 后端回归测试证明本地扫描不会调用 K 线联网函数或 Baostock 登录，并证明旧版默认值仍为 `baostock`。
- 前端单元测试证明默认来源为本地、切换来源时周期和功能约束正确。
- 运行平台扫描、存储、取消相关测试，运行前端生产构建和 `git diff --check`。
- 浏览器检查来源切换、禁用状态、文案和布局。

## Tasks

1. 写前后端失败测试，锁定离线边界和旧版兼容边界。
2. 新增后端数据源 owner，并让平台扫描器支持本地只读 K 线。
3. 将异步扫描任务接到数据源 owner，历史记录保存来源。
4. 更新平台扫描页，默认本地并保留旧版联网切换。
5. 完成回归测试、构建和浏览器验证。

## Repair Track

- 根因：`ScanView.vue` 固定调用 `/api/scan/start`，该端点固定通过 `BaostockConnectionManager` 和 `fetch_kline_data` 获取全部数据，没有本地来源分支。
- 修复 owner：平台扫描的数据源选择层，而不是在前端伪装文案或拦截网络请求。
- 验证：本地模式对所有 Baostock 入口设置失败哨兵，扫描仍能完成。

## Retirement Track

- 旧联网路径仍为显式对比功能，并继续服务 `#/legacy` 和未升级客户端，因此暂不删除。
- 本地模式不增加联网回退；本地数据缺失时明确报错并引导到数据管理页同步。
- 当旧版页面和外部客户端确认不再使用后，才可另立任务评估移除 Baostock 默认兼容行为。
