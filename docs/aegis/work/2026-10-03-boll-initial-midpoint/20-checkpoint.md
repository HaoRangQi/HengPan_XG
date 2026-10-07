# 布林初始中点复核与连续扩展 - Checkpoint

- Task ID: 2026-10-03-boll-initial-midpoint
- Current todo: 先更新行为测试并证明旧实现失败
- Active slice: tests
- Blocked on: none
- Next step: 写失败回归，再替换搜索逻辑

## Checkpoint Update

- Current todo: 运行完整回归并核对服务加载新算法
- Active slice: verification
- Completed todos:
- 新行为测试已证实旧实现失败；30 项布林测试在修正后通过
- Evidence refs:
- api/hengpan/tests/test_boll_endpoints.py
- api/hengpan/tests/test_boll_box.py
- Blocked on: none
- Next step: 后端全套、前端全套、构建；检查相对接手快照的改动

## DriftCheckDraft

- Scope status: 符合用户确认的三步算法，中点仅检查第一次，扩展步长为 1
- Compatibility status: 参数和结果 schema 不变；旧历史不重算；大图显示设置不变
- Retirement status: 最长到最短、失败后继续寻找的旧循环已删除
- New risk signals:
- none
- Advisory decision: continue

## Checkpoint Update

- Current todo: 完成
- Active slice: complete
- Completed todos:
- 新规则实现、专项与完整回归、页面说明更新、构建、服务重启及读回均完成
- Evidence refs:
- /tmp/hengpan-boll-python-tests.log
- /tmp/hengpan-boll-node-tests.log
- /tmp/hengpan-boll-build.log
- Blocked on: none
- Next step: 用户刷新页面后重新发起布林扫描
