# 本地行情存储收口

## Requested outcome

接续 Claude 中断的本地化存储实现，完成 60 分钟行情的本地同步、读取、横盘扫描接线和数据管理操作。

## Scope

- 保留既有 `api/data/market.db` 与已写入行情。
- 修复同步取消、进程回收、断点续传和重复任务问题。
- 确保横盘扫描只读 SQLite，不在逐只读取时执行建表或改视图。
- 补齐数据管理页中设计文档列出的同步与维护入口。

## Baseline read set

- `docs/local-storage-v1-60m.md`
- `api/store/*.py`
- `api/hengpan/router.py`
- `api/hengpan/scanner.py`
- `src/views/DataView.vue`
- 当前 Git diff 与 `api/data/market.db` 表结构、同步日志

## Impact and risk

跨后端存储、后台任务、多进程和前端管理页。主要风险是取消后遗留子进程、重复全市场请求、SQLite 读路径误写，以及维护操作误删范围。

ArchitectureReviewRequired: yes
