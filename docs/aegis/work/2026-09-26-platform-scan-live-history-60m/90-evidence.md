# 证据包

## Automated checks

- `api/.venv/bin/python -m compileall -q api`：通过。
- `npm run build`：通过；Vite 仅报告已有的大 bundle 与 Browserslist 提示。
- `git diff --check`：通过。
- API 契约冒烟：历史两个路由存在，`frequency='60'` 接受，非法周期拒绝。
- 任务管理器：streamed 结果会并入终态 `result`。
- 历史存储：原子 JSON 写入、元数据列表、详情读取往返通过。
- 扫描器模拟：按完成顺序回调；60 分钟少于窗口根数跳过；停止保留已发现结果。
- 历史详情时间戳转换修复后重新通过前端构建。
- 历史详情恢复周期/窗口修复后重新通过前端构建，在线历史 API 仍可访问。
- `20260926103000000`、`103000` 等分钟时间格式归一化测试通过；后端重启后 `127.0.0.1:8001` 在线。

## Live services

- `127.0.0.1:8001` 正在监听，`GET /api/scan/history` 返回 `{"histories":[]}`。
- `127.0.0.1:5173` 正在监听，页面入口可返回。

## Not covered

- 浏览器无法启动：桌面处于锁屏状态且 CUA 报告 Codex auth token unavailable。
- Baostock 真实 60 分钟拉取未验证：当前账号此前返回“黑名单用户”。
