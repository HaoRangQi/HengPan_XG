# Proof Bundle - 2026-10-03-boll-initial-midpoint

## Method Pack Boundary

This proof bundle is an advisory Aegis Method Pack record. It does not determine evidence sufficiency, produce authoritative `GateDecision`, or grant `completion authority`.

## Task Intent

- Requested outcome: 最近 B 根先验四点，再验一次中点左右两半；逐根向前扩展，首次失败即停止。
- Scope: 共享布林算法、双市场回归测试、规则说明与 API 描述

## Impact

- Compatibility boundary: 保留现有参数、返回字段、四点绘图和历史记录；新规则用于重新扫描。
- Non-goals:
- 不反复检查中点，不新增步长设置，不改均线算法和大图设置。

## Evidence Bundle Refs

- docs/aegis/work/2026-10-03-boll-initial-midpoint/evidence-bundle-draft-red.json
- docs/aegis/work/2026-10-03-boll-initial-midpoint/evidence-bundle-draft-regression.json
- docs/aegis/work/2026-10-03-boll-initial-midpoint/evidence-bundle-draft-service.json

## Drift Check

- Scope status: 符合用户确认的三步算法，中点仅检查第一次，扩展步长为 1
- Compatibility status: 参数和结果 schema 不变；旧历史不重算；大图显示设置不变
- Retirement status: 最长到最短、失败后继续寻找的旧循环已删除
- Advisory decision: continue
