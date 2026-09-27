# 检查点

## TodoCheckpointDraft

- [completed] 增量扫描结果立即展示并合并到终态结果。
- [completed] 增加停止扫描并保留已发现结果。
- [completed] 保存、列出、加载历史扫描快照。
- [completed] 接入日线与 60 分钟 K 线周期。
- [completed] 完成 API、构建与模拟验证。
- [needs-verification] 浏览器真实 UI 点选验证。

## ResumeStateHint

业务代码改动已完成；若任务中断，从 `npm run build`、Python 模拟验收和运行中服务状态继续，不要重置用户已有工作树改动。

## Evidence refs

- `api/.venv/bin/python -m compileall -q api`
- `npm run build`
- `git diff --check`
- TaskManager/history/build_result_stock 模拟脚本通过。
- Scanner `as_completed`、60 分钟窗口不足、停止保留结果模拟脚本通过。
- 历史详情 Unix 秒时间戳已统一转换为前端毫秒，避免历史用时显示异常。
- 历史详情加载会恢复保存时的 `frequency`、`windows` 和进度统计，保证 60 分钟历史显示“根 K 线”。
- 60 分钟 `time` 字段已规范化为 `HH:MM:SS`，并已重启后端加载最新代码。

## DriftCheckDraft

- Scope: continue
- Compatibility: `frequency` 默认日线；旧同步接口保留。
- New owner: `api/scan_history.py` 独占 JSON 快照持久化。
- Retirement: 旧“扫描中只显示进度”和“停止即结束轮询”路径退出主流程。
- Decision: needs-verification（浏览器自动化受锁屏/令牌阻断）。
