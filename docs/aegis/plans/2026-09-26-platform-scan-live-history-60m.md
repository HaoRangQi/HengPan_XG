# 平台期扫描实时结果、历史快照与 60 分钟周期实施计划

## Goal

让长时间扫描在发现股票后立即展示，支持安全停止并保留已发现结果；自动持久化完成/停止的扫描快照并可重新加载；在保留日线的同时增加 60 分钟 K 线扫描，并将窗口值解释为对应周期的天数或 K 线根数。

## Architecture

- 扫描任务仍由 `api/task_manager.py` 管理，`api/index.py` 负责异步任务 API。
- `api/platform_scanner.py` 负责逐股取数与分析，通过回调把发现结果和进度交给任务层。
- `api/data_fetcher.py` 提供可选频率的 Baostock K 线查询。
- 新增 `api/scan_history.py` 作为扫描快照的唯一持久化 owner，使用 `api/data/scan_history/*.json`。
- `src/views/ScanView.vue` 负责周期选择、增量结果渲染、停止收口和历史快照选择。

## Tech Stack

- FastAPI + Pydantic + Baostock + pandas
- Vue 3 + Vite + Axios + Tailwind CSS

## Baseline/Authority Refs

- `api/index.py` 的 `/api/scan/start`、`/api/scan/status/{task_id}`、`/api/scan/cancel/{task_id}`
- `api/task_manager.py` 的任务状态与 streamed cursor
- `api/platform_scanner.py` 的 `scan_stocks` 回调和逐股分析链路
- `src/views/ScanView.vue` 的现有轮询与结果卡片
- `api/case_manager.py` / `api/case_api.py` 的 JSON 文件存储和列表/详情 API 模式

## Compatibility Boundary

- 保留日线默认行为、现有异步扫描接口、旧同步 `/api/scan` 接口和案例保存接口。
- 新的 `frequency` 字段默认值为 `d`；未传该字段的旧客户端行为不变。
- 停止只取消尚未开始的工作，不强杀正在进行的 Baostock 请求；最终状态为 `cancelled`，结果仍可读取。
- 历史快照不替代案例库；快照保存完整扫描结果和参数，单只股票仍可另存为案例。

## Verification

- Python 单元测试：任务取消与 streamed cursor、历史快照写入/列表/读取、频率参数透传和 60 分钟窗口数据量校验。
- 前端构建：`npm run build`。
- API 冒烟：启动、状态增量、停止收口、历史列表/详情、日线兼容、60 分钟参数校验。
- 浏览器验证：扫描中出现结果卡片、停止后结果保留、历史选择恢复结果、周期选择切换标签和说明。

## Tasks

1. 修复扫描任务增量/停止收口，确保结果逐只进入最终结果集。
2. 增加扫描快照存储与历史 API，并在任务结束时自动保存。
3. 为 K 线抓取和分析链路增加 `frequency`，支持日线与 60 分钟。
4. 更新扫描页交互：扫描中显示结果、停止按钮状态、历史选择器、周期选择与单位文案。
5. 联调 API、前端和构建，核对旧接口兼容性。

## Risks

- Baostock 对分钟级数据的历史范围和权限可能比日线更严格；无法返回足够根数时必须明确报错，不得静默用日线替代。
- JSON 快照可能包含较大的 K 线数组；列表接口只返回元数据，详情接口才返回完整结果。
- 进程重启不会恢复正在执行的任务，但已写入的历史快照应保留。

## Repair Track

- 修复 owner：扫描任务 API 与前端轮询收口逻辑。
- 最小修复：让增量结果在 `running` 状态直接渲染，停止后继续取到终态并用最终结果覆盖/合并。
- 验证：模拟任务状态序列和真实 API 冒烟。

## Retirement Track

- 旧的“扫描中仅显示进度”和“停止后立即结束轮询”路径退出主流程。
- 旧同步接口保留作为兼容边界；只有现有调用全部迁移后才考虑删除。

