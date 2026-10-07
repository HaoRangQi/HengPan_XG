# 前八项修复实施计划

目标：按已批准方案修复前八项，优先长时内存。
架构：延用 Vue/FastAPI/SQLite；案例独立数据库，任务统一拥有元信息和缓存，历史为已完成结果的持久来源。
基线：AGENTS、README、PRODUCT、8f066f9 加现有工作区。
兼容：develop；保留既有改动；不改研究逻辑第九项。

1. 案例：api/case_manager.py、case_api.py、新 case_store.py 及 tests；先复现 ID 冲突/越界/部分写，再事务存储、备份迁移与回归。
2. 内存：api/task_manager.py、四个扫描路由、history；先验证重复结果复制、清理缺失、元数据滞留，再增加有界持久缓存与回收；历史失败不可丢弃。
3. 数据：store.reader、scanner、crypto scanners、参数页面；用 stale/ST unknown/不同单位样本验证，再共享数据检查、明确 bars 与日历约束。
4. 阈值：box_detector 与 combined_analyzer；0.55/0.5/0.6 边界先失败，再统一最终判定。
5. 结果：超过400命中与随机完成序；完整持久保存、摘要分页和按需图表，不让候选重新进入最终集合。
6. 前端：App.vue、四扫描视图、图表组件；行为与生命周期测试先行，再提取轮询/资源管理，停止隐藏页无效工作，按需加载页面。
7. 验证：全套 unittest、node test、npm build；反复大扫描和刷新/切页资源检查。每片记录结果，CHANGELOG同步。

回退：保留旧案例文件备份和当前工作区差异；新存储失败明示且不可破坏原始数据。提交只包含本次可分离改动，已有混合改动不擅自打包。
