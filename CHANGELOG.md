# Changelog

记录项目每次提交的历史改动，按新到旧排列。历史条目依据 Git 提交日期和原始标题补录；原始标题未说明的细节不作推断。

## 维护规则

- 每次提交必须在本文件新增条目，并与对应改动一起提交，包含日期、提交标题、改动内容和验证情况。
- 当前提交不填写自身 SHA（提交前尚不存在），用日期和唯一标题关联；后续可补充已有提交的短 SHA。
- 功能、修复、重构、文档及配置提交均需记录；工作区未提交内容不得标成已完成。
- 开发统一使用 `develop`，`main` 保留为稳定分支。暂不保留其他长期开发分支。

## 未提交工作

以下仅为当前工作区提示，尚未纳入本次分支整理提交，也不代表已发布：

- 均线走平、布林箱体及相关规则、图表和测试改动。
- 扫描历史清理、图表窗口及提示等调整。
- 相关研究、部署方案与工作记录。

提交这些改动时，应按实际 diff 拆分并补充正式条目，随后移除对应提示。

## 2026-10-06 — chore: 统一 develop 开发分支并建立提交变更记录

- 将当前开发线统一命名为 `develop`，保留既有提交历史；保留 `main`。
- 补录此前 39 次提交，建立每次提交同步维护 changelog 的规则。
- 更新 README 获取分支与开发约定，并为后续代理工作补充提交规则。
- 验证：旧开发分支提交均已被当前开发线包含；历史补录与 `git log` 对照。分支推送及清理结果以 Git 远程引用核验。
- 范围：仅分支与文档整理，不纳入现有未提交功能改动。

## 历史提交（补录）

| 日期 | 提交 | 改动（原始提交标题） |
| --- | --- | --- |
| 2026-09-30 | `102a9dc` | feat: 完善横盘案例保存与大图查看 |
| 2026-09-30 | `86c24fb` | feat: 统一四类扫描历史与管理入口 |
| 2026-09-30 | `3e7b26a` | fix: 放开横盘箱体宽度限制并保留数值精度 |
| 2026-09-28 | `261be3b` | fix: raise crypto thumbnail chart window |
| 2026-09-28 | `028ef43` | fix: make crypto chart windows configurable |
| 2026-09-28 | `dc8fd64` | fix: keep crypto volume analysis opt-in |
| 2026-09-28 | `d103b51` | docs: rewrite local setup guide |
| 2026-09-28 | `f534032` | release: 1.0.0 |
| 2026-09-28 | `d5fab10` | feat: 添加加密-U本地平台扫描 |
| 2026-09-28 | `2e57afb` | fix: 过滤容刺箱体中的台阶换挡 |
| 2026-09-28 | `5af8878` | feat: 默认使用容刺箱体模式 |
| 2026-09-28 | `eb051d0` | feat: 添加横盘多模式与容刺箱体 |
| 2026-09-28 | `9a619b9` | fix: 为加密行情补充周期导航 |
| 2026-09-28 | `8ffa831` | feat: 添加数据行情周期导航 |
| 2026-09-28 | `04dbdf4` | fix: 对调横盘U与平台A页面 |
| 2026-09-28 | `43deda4` | fix: 按导航规划调整占位页面 |
| 2026-09-28 | `fa76f06` | feat: 调整扫描布局与导航 |
| 2026-09-28 | `cbe8a26` | fix: 平台扫描默认读取本地行情 |
| 2026-09-28 | `baa642b` | fix: 完善K线中文行情提示 |
| 2026-09-28 | `94b181c` | fix: 区分大图K线上涨与下跌颜色 |
| 2026-09-28 | `5a94dc5` | feat: 增强行情蜡烛图与涨跌信息 |
| 2026-09-28 | `70488f6` | feat: 支持删除和清理横盘扫描历史 |
| 2026-09-28 | `9616e73` | feat: 增加横盘扫描振幅上限 |
| 2026-09-28 | `86496ee` | docs: 调研加密扫描复用 A 股双模式 |
| 2026-09-28 | `66191b4` | fix: 规则表只显示当前箱体模式用得到的字段 |
| 2026-09-28 | `37278d4` | feat: Material You 界面重设计 + 加密货币行情库 |
| 2026-09-28 | `b237864` | feat: 本地 60 分钟行情库，扫描改读本地，数据管理页重做 |
| 2026-09-27 | `fcebf93` | fix: 修复扫描无法停止、后端进程空转的问题 |
| 2026-09-27 | `887901d` | feat: 新增横盘选股页并改进平台期扫描 |
| 2025-05-25 | `cbf3d64` | feat: Realize the pagination function of stock data, add a pagination controller and related status management, and update the rendering logic of the stock list to support pagination display. |
| 2025-05-24 | `47d7abd` | 更新 vite.config.js 以支持环境变量 VITE_API_URL，并将服务器主机设置为 0.0.0.0；移除 api/run.py 中的重复导入。 |
| 2025-05-06 | `4fc8535` | Update index.py |
| 2025-05-06 | `a24526f` | Update requirements.txt |
| 2025-05-06 | `2447974` | fix: upload index.html |
| 2025-05-06 | `ad29056` | Update .gitignore |
| 2025-05-06 | `5e0022e` | Update README.md |
| 2025-05-06 | `b0271e6` | Add tqdm to requirements for progress bar support |
| 2025-05-06 | `7a3392f` | Add comprehensive stock analysis modules |
| 2025-05-05 | `3b8e2b4` | first commit |
