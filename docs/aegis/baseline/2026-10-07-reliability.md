# 可靠性修复后的责任边界

- api/task_manager.py：状态、终态权威结果、元信息、回收、重启恢复。
- api/task_results.py：磁盘结果缓存、分页和按标的K线读取。
- api/task_api.py：分页结果、缓存过期历史回读、保存重试。
- api/history/store.py：持久历史和流式保存，不能由路由另存一套历史。
- api/case_store.py：案例SQLite事务及一次性旧库迁移。
- api/data_quality.py：已收盘、时点、连续性和逐窗口数据量检查。
- api/scan_parameters.py：新旧窗口参数兼容与语义版本。
- src/scan/：轮询、按需图表数据、参数语义及历史保存反馈；业务规则仍由对应页面/后端拥有。

当前分支develop；main保留。原有未提交均线/布林和历史改动仍保留，不单独撤销或擅自打包。

公共新增契约：compact=true状态、/api/tasks/{id}/results、/kline/{code}、/history/retry、/status。薄结果带kline_url；ST状态允许null；参数版本2使用显式bar单位。

测试：unittest api发现、node --test全部*.test.js、Vite build、任务压力与重启回归、浏览器烟测。该基线对应ADR0001。
