# 布林初始中点复核与连续扩展 - Intent

## TaskIntentDraft

- Requested outcome: 最近 B 根先验四点，再验一次中点左右两半；逐根向前扩展，首次失败即停止。
- Goal: 最近 B 根先验四点，再验一次中点左右两半；逐根向前扩展，首次失败即停止。
- Success evidence:
- none
- Stop condition: Stop when success evidence is satisfied or a blocker/risk requires pause.
- Non-goals:
- 不反复检查中点，不新增步长设置，不改均线算法和大图设置。
- Scope: 共享布林算法、双市场回归测试、规则说明与 API 描述
- Change kinds:
- behavior
- Risk hints:
- none

## BaselineReadSetHint

- api/hengpan/boll_box.py
- src/hengpan/ruleModes.js

## ImpactStatementDraft

- Compatibility boundary: 保留现有参数、返回字段、四点绘图和历史记录；新规则用于重新扫描。
- Affected layers:
- none
- Owners:
- api/hengpan/boll_box.py
- Invariants:
- none
- Non-goals:
- 不反复检查中点，不新增步长设置，不改均线算法和大图设置。

These records are Method Pack drafts / hints, not authoritative runtime decisions.
