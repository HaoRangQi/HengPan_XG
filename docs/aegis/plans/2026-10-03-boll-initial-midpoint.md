# 布林初始中点复核与连续扩展

- Goal：落实本轮已确认的三步判定。最近 B 根首尾合格后，只做一次中点左右两半复核；之后逐根向历史扩展，首次不合格即停止。
- Architecture：`api/hengpan/boll_box.py` 是唯一算法 owner，A/U 扫描共用。保留 `endpoints_v1`，它表示最终轮廓的四点绘图形状，不表示中点已被绘制。
- Tech Stack：Python/NumPy、FastAPI/Pydantic、Vue、Node test runner。
- Baseline/Authority Refs：用户本轮确认；`README.md`；`docs/aegis/BASELINE-GOVERNANCE.md`；当前算法、两组布林测试和 `src/hengpan/ruleModes.js`。
- Compatibility Boundary：A+B 取数约定、布林计算方法、矩形容差公式和输出结构不变；旧历史按原结果展示，不自动重算；新扫描使用新算法。中点为初始区间索引 `(start + end) // 2`，偶数长度选靠左中点。步长固定为 1。
- Verification：后端完整 unittest、前端完整 node 测试、Vite build、服务重启后 HTTP 与真实扫描函数检查。

## 风险与边界

TDD Route：auto / strict。ArchitectureReviewRequired：yes。变化涉及核心判定，但 API 字段、数据流和模块归属保持原样。

原函数约 120 行，主要包含计算和返回指标；抽取模块内矩形误差 helper，避免整体、左右半段、扩展阶段重复实现同一公式。两份 1500 行左右 Vue 页面仅替换说明文案，不添加算法。

Repair Track：共享算法增加初始门槛和一次中点检查，改成向前逐根扩展。
Retirement Track：删除从最长到最短枚举、失败后继续寻找的旧循环；不保留旧算法开关。历史展示保留原几何字段。

## 执行步骤

1. 更新 `api/hengpan/tests/test_boll_endpoints.py` 和 `test_boll_box.py`：拒绝初始失败与中点失败；首个坏点截断；中点不随扩展重算；奇偶中点、退化箱高、缩放精度、双市场和历史字段回归。
   验证 RED：`api/.venv/bin/python -B -m unittest api.hengpan.tests.test_boll_endpoints api.hengpan.tests.test_boll_box -v`，应因旧搜索行为产生断言失败。
2. 在 `boll_box.py` 提取矩形误差计算，保留原容差和零箱高处理。以初始起点为 `chosen`，依次检查 `(chosen, tail)`、`(chosen, midpoint)`、`(midpoint, tail)`；任何一项失败就不扩展。通过后从 `chosen - 1` 递减到 1，每次只检查 `(candidate, tail)`，首次失败 `break`，成功则更新 `chosen` 和最终首尾误差。
   验证 GREEN：重跑上述两组测试。返回 `box_bars`、四点、起止日期、均值和 `history_limited` 均以最后接受的起点计算。
3. 更新 `ruleModes.js`、两份 HengpanScanView 和 `router.py` 中旧算法说明。历史结果区仅说明四点几何，不把旧结果宣称为已完成新中点复核。
4. 运行 `api/.venv/bin/python -B -m unittest discover -s api -p 'test_*.py'`、`node --test src/*.test.js src/**/*.test.js`、`npm run build`、`git diff --check`。
5. 对照接手快照检查实际改动，记录证据；重启本项目后端，使正在运行的服务加载新逻辑，并检查页面与 API。保留当前未提交工作，不混合提交其他既有改动。
