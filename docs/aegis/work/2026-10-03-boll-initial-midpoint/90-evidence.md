# 布林初始中点复核与连续扩展 - Evidence

No evidence has been recorded yet.

## EvidenceBundleDraft

- Artifact key: red
- Type: test
- Source: api/.venv/bin/python -B -m unittest api.hengpan.tests.test_boll_endpoints api.hengpan.tests.test_boll_box -v
- Summary: 旧算法运行 29 项测试，出现 10 个预期断言失败，覆盖初始门槛、中点两半、首坏点截断。
- Verifier: Codex

## EvidenceBundleDraft

- Artifact key: regression
- Type: test
- Source: /tmp/hengpan-boll-python-tests.log; /tmp/hengpan-boll-node-tests.log; /tmp/hengpan-boll-build.log
- Summary: 305 项后端测试、90 项前端测试通过；生产构建成功。布林专项 30 项包含新行为双市场集成和历史往返。构建存在原有 bundle 体积及 Browserslist 数据过旧提示。
- Verifier: Codex

## EvidenceBundleDraft

- Artifact key: service
- Type: runtime
- Source: http://127.0.0.1:18001/; http://127.0.0.1:15173/api/openapi.json; http://127.0.0.1:15173/src/hengpan/ruleModes.js
- Summary: 后端重启为 PID 77430；健康检查、前端、代理 schema、规则资源、扫描历史接口均 HTTP 200；schema 和 Vite 资源读回新规则说明。
- Verifier: Codex
