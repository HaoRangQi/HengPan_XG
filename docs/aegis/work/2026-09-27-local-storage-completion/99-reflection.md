# Reflection

## Repair track

- 进程池取消原先使用 `shutdown(wait=False)`，异常或父进程退出后可能留下工作进程。现在由 `api/process_pool.py` 在取消和异常时终止、等待并兜底 kill，正常路径等待干净退出。
- 逐只本地扫描原先通过普通连接反复执行建表和重建视图。现在使用 SQLite `mode=ro` 连接，读取路径不再改结构。
- 完整复权因子原先只能按板块整体完成，取消后会从头请求；现在用 `adjust_factor_sync` 按证券续传。每日复权用交易日游标避免重复请求空日期。
- 路由层现在只允许一个本地同步任务，页面刷新能恢复活动任务，写维护操作会在同步期间被拒绝。

## Retirement track

- 退役各扫描器中直接 `shutdown(wait=False)` 的进程池收口路径，统一交给 `close_process_pool`。
- 退役扫描子进程的普通 `open_db` 读取路径，改用 `open_readonly_db`。
- 保留日线扫描实时联网路径；其删除触发条件是后续日线本地化版本完成并验证结果一致。

## Architecture alignment

实现仍以 `docs/local-storage-v1-60m.md` 为基线：同步模块是唯一联网写入所有者，读取层负责类型与复权，60 分钟扫描只读本地，管理页承载显式维护操作。新增断点表和进程池收口已回写设计文档，无需单独 ADR。

## Residual risk

- 未执行全市场首次同步，因此 Baostock 长时间批量链路、真实取消时延和完整前复权一致性尚未在本轮重新验证。
- 未运行自动化测试套件；本轮证据覆盖编译、构建、只读 API、数据库保全和桌面布局。
- `DataView.vue` 已增至约 579 行，当前仍围绕单一数据管理页面，但后续增加日线或更多周期时应拆出本地行情管理组件。

## Port migration

项目默认开发端口改为前端 `15173`、后端 `18001`。Vite 仍支持 `VITE_PORT` 和 `VITE_API_URL` 覆盖，Python 启动入口支持 `API_PORT` 覆盖。
