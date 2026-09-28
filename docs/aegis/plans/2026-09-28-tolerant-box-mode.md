# 横盘多模式与容刺箱体实施计划

**Goal:** 将横盘规则编辑器按模式拆分，并增加基于实体中心价的容刺箱体扫描。

**Architecture:** `HengpanScanView.vue` 保留公共扫描流程；三个规则编辑器分别拥有模式字段；`ruleModes.js` 统一默认值、标签和兼容归一化；`tolerant_box.py` 独立拥有第三算法；扫描器按 `box_type` 分派。

**Tech Stack:** Vue 3、原生 Node test、FastAPI/Pydantic、NumPy/Pandas、unittest。

**Baseline/Authority Refs:** `横盘思路3.md`、本次对话确认、`docs/aegis/specs/2026-09-28-tolerant-box-mode-brief.md`。

**Compatibility Boundary:** 旧 `fixed`/`amplitude` 合约和结果不变；旧历史缺字段可读；后端保留混合规则能力。

**Verification:** Python 横盘单测、全部前端 Node 测试、`npm run build`、`git diff --check`。

## 文件边界与压力检查

- 新建 `api/hengpan/tolerant_box.py`：只负责容刺箱体纯计算。
- 修改 `api/hengpan/scanner.py`：按规则类型分派和统计，不承载算法细节。
- 修改 `api/hengpan/router.py`：扩展请求/响应契约和判重。
- 新建 `src/hengpan/ruleModes.js` 与三个 `src/hengpan/rules/*RuleEditor.vue`：模式状态与规则 UI。
- 修改 `src/hengpan/HengpanScanView.vue`：移除内嵌规则表，接入动态组件。
- 压力结论：主页面超过 800 行，必须抽组件；后端第三算法必须新增 owner 文件，不扩张 `anchored_box.py`。

## 任务

### 1. 容刺算法（TDD）

- [ ] 在 `api/hengpan/tests/test_tolerant_box.py` 写正常覆盖、影线、实体刺、连续刺、边界、数据不足测试。
- [ ] 运行该测试并确认因模块不存在而 RED。
- [ ] 新建 `api/hengpan/tolerant_box.py`，实现实体中心价最大覆盖窗口与连续刺判断。
- [ ] 运行目标测试确认 GREEN。
- [ ] 提交时与其消费端一起提交，避免中间提交破坏主分支。

### 2. API 与扫描接线（TDD）

- [ ] 扩展请求和扫描器测试，确认 `tolerant` 尚未被接受。
- [ ] 修改 `router.py` 和 `scanner.py`，分派新算法并保持旧参数兼容。
- [ ] 运行全部 `api.hengpan.tests`。
- [ ] 检查旧 `fixed`/`amplitude` 测试结果无变化。
- [ ] 提交时纳入最终功能提交。

### 3. 前端模式工具与独立组件（TDD）

- [ ] 为 `ruleModes.js` 写默认值、有效字段、归一化和模式切换缓存测试，确认 RED。
- [ ] 实现工具模块与三个规则编辑器。
- [ ] 将主页面规则表替换为顶层模式选择和动态组件，补齐 payload、历史恢复、标签和说明。
- [ ] 运行全部前端测试确认 GREEN。
- [ ] 运行构建，修复模板或类型错误。

### 4. 完成验证与提交

- [ ] 运行 Python 横盘测试、全部前端测试、生产构建和 `git diff --check`。
- [ ] 检查 diff 中未改动数据源、旧版页面和用户的 `横盘思路3.md` 内容。
- [ ] 更新 Aegis 索引并检查工作区文档。
- [ ] 提交全部改动并推送 `feat/local-store-60m`。
- [ ] 报告自动化覆盖与仍需人工扫描验证的风险。

## 风险与退役

- 旧内嵌混合规则编辑表由三个模式组件取代；后端混合规则合约保留，作为旧客户端兼容边界。
- 容刺模式默认口径按实体刺判断，`breach_full` 只保留影线越界观察值，不能用它淘汰结果。
- 本轮不删除 `anchored_box.py` 的任何旧模式，不改变历史快照文件格式版本。
