# 任务意图与基线

## Requested outcome

长时间平台期扫描需要在发现股票后立即展示，支持停止并保留已发现结果；完成或停止后保存可重新加载的历史快照；保留日线并新增 60 分钟 K 线扫描，窗口值按所选周期解释。

## Scope

- 后端异步扫描、取消、增量结果、历史列表与详情。
- Baostock 日线/60 分钟字段与窗口根数校验。
- Vue 扫描页周期选择、实时结果、停止按钮和历史恢复。

## Non-goals

- 不替换 Baostock 数据源。
- 不删除旧同步 `/api/scan` 接口。
- 不改变用户已设定的默认窗口、阈值和创业板范围。

## BaselineReadSetHint

- `api/index.py`
- `api/task_manager.py`
- `api/platform_scanner.py`
- `api/data_fetcher.py`
- `src/views/ScanView.vue`
- `docs/aegis/plans/2026-09-26-platform-scan-live-history-60m.md`

## ImpactStatementDraft

这是跨模块契约变更：任务状态增加可消费的 streamed 结果和历史快照字段，新增 `frequency` API 参数，并由前端轮询消费。默认 `frequency='d'` 保持兼容。

