# Docker 部署兼容研究与落地方案

> 归档提示（2026-10-07）：本文保留 10 月 5 日的研究快照。后续代码已更新任务缓存、恢复与案例存储，部署前应按当前实现复核；本文本身不代表 Docker 支持已落地。

日期：2026-10-05\
对象：`2_a-share-platform-stocks-selection`\
状态：研究建议，尚未实施 Docker 支持；文中的新增文件、配置和接口均为拟议设计。\
研究基准：当前工作区，Git HEAD 为 `102a9dc`，包含已有未提交修改及未跟踪的布林、均线模块，不等同于远端仓库或纯 HEAD。\
ArchitectureReviewRequired：yes；本轮仅交付研究，不改变运行架构，不将建议登记为已采纳 ADR。

## 1. 结论

项目适合增加 Docker 模式，不需要重写前后端，也不需要为这两个场景引入 Redis、Celery 或 PostgreSQL。

推荐首版：**Nginx 静态前端 + 单个 FastAPI 服务进程 + 两个 Docker 命名卷 + 一份 Compose**。

- 场景 A：进入项目目录执行 `docker compose up -d`，首次自动构建，打开 `http://localhost:8080`。宿主机只需 Git 和已启动的 Docker Engine/Compose，不需要 Python、Node、SQLite。
- 场景 B：同一份 Compose，设置 `APP_BIND=0.0.0.0` 后启动，多人访问 `http://服务器地址:8080`；可接已有域名和 HTTPS 反向代理，不增加认证。
- 所有人共享同一个工作台和服务端数据。多人访问不等于无限并行扫描：首版全局同时只运行一个重任务，忙时直接返回明确冲突信息，普通本地查询继续服务。
- 数据卷保留行情、扫描历史、K 线快照和案例；升级镜像不清数据。正在执行的任务不支持重启后自动续跑，已提交的同步数据和已完整保存的历史保留。
- 原有本地开发模式继续保留。Docker 使用生产构建和 Uvicorn 正式启动参数。

**不能只增加 Dockerfile 就宣布场景 B 完成。** 任务状态是进程内存，案例文件存在秒级 ID 冲突风险，Binance 禁用环境代理，停止过程没有应用级统一收口；这些都必须纳入落地范围。

## 2. 范围和成功标准

### 两种使用场景

| 项目 | A：用户自己的电脑 | B：服务器多人访问 |
| --- | --- | --- |
| 使用入口 | `localhost:8080` | 服务器 IP/域名 |
| 必需安装 | Docker Engine + Compose；获取仓库可用 Git | Docker Engine + Compose |
| 首次命令 | `docker compose up -d` | 修改监听配置后，同一条命令 |
| 后端、SQLite | 自动启动、自动建表 | 同左 |
| 行情初始化 | 首次进入“数据”页主动同步 | 任意使用者同步一次，所有人共享 |
| 用户体系 | 无账号 | 无账号、角色、权限、用户隔离 |
| 数据语义 | 当前 Docker 实例私有 | 实例内所有人共享 |
| 配置差别 | 默认只绑定回环地址 | 绑定服务器网卡，放行所选入口端口 |

首版不做：登录、多租户、每人独立数据、分布式任务队列、多副本、自动定时同步、任务故障续跑、Kubernetes、强制镜像仓库发布、域名证书自动签发、任意 URL 子路径部署。

成功标准是：干净仓库能启动；持久化覆盖完整；另一台机器能正常使用；多客户端同时操作时不出现任务串线、案例 ID 覆盖或无上限派生进程；重建和备份恢复有可复现步骤。

### 研究依据与限制

阅读了当前 README、PRODUCT、Aegis 治理文件、启动入口、路由、任务管理、行情库、历史库、案例存储、Binance/Baostock 连接和相关前端请求。`docs/aegis/baseline/` 当前未发现可用快照，技术事实以现有源码为准；README 的“本地部署”是现状，不代表不能增加 Docker。

当前工作区有较多既有修改。本研究没有修改它们，也没有把它们打包发布。实施前必须确定包含完整功能的发布提交，避免本机依赖未跟踪文件而干净克隆失败。

## 3. 当前代码事实与 Docker 影响

下列路径相对于项目根目录；定位采用文件和符号，避免未提交修改导致行号漂移。

| 事实 | 代码依据 | 部署影响 |
| --- | --- | --- |
| Vue 3 + Vite；生产输出 `dist/` | `package.json`、`vite.config.js` | 构建阶段需要 Node，运行阶段只需静态服务器 |
| 构建有 `index.html`、`data.html` 两个入口；主界面用 hash 路由 | `vite.config.js`、`src/App.vue` | 两个入口都必须复制；主界面无需复杂路径重写 |
| 常规接口使用相对 `/api/...` | `src/views/ScanView.vue`、`src/hengpan/*ScanView.vue`、`src/views/data/LocalStorePanel.vue` | 统一域名和端口即可兼容本地、远程访问 |
| `VITE_API_URL` 只被 Vite 开发代理读取 | `vite.config.js → server.proxy` | 静态镜像运行时设置这个变量不会改变后端地址 |
| FastAPI 入口 `api.index:app` | `api/index.py` | 容器可以从 `/app` 直接启动 |
| `api/run.py` 绑定 `127.0.0.1`、启用 reload | `api/run.py` | 不作为容器正式入口；容器内需绑定 `0.0.0.0` |
| 任务存于 `_tasks`，部分路由还有 `_extras` | `api/task_manager.py`；横盘、加密扫描 router | API 必须单 worker、单副本，否则轮询/取消可能找不到任务 |
| 扫描通过 `BackgroundTasks` 执行，部分算法内部创建进程池 | `api/index.py`、`api/hengpan/router.py`、`api/platform_scanner.py`、`api/hengpan/scanner.py` | 一个 API worker 不等于一个计算进程；仍要限制单任务进程数和总任务数 |
| A 股和加密同步各自有 `_sync_guard` | `api/store/router.py`、`api/crypto/router.py` | 已防同市场重复同步，但不限制全部扫描、跨市场任务、补拉 |
| 三个 SQLite 库使用 WAL | `api/store/db.py`、`api/crypto/db.py`、`api/history/db.py` | 适合单机共享读；不能等同多写者无冲突 |
| 案例目录在仓库根部 `cases/` | `api/case_manager.py → CASE_DIR` | 只挂载 `api/data/` 会漏数据 |
| 案例 ID 默认 `case_<秒时间戳>`，JSON 直接覆盖写 | `api/case_manager.py → create_case/update_case/delete_case` | 同一秒两个请求也能冲突；应修复 ID 与写入原子性 |
| Baostock socket 保存在库级全局 context | `api/baostock_patch.py`、`api/data_api.py → _bs_lock` | 线程局部登录标记不能证明 socket 隔离；预览、补拉、扫描需协调 |
| Binance 显式 `ProxyHandler({})` | `api/crypto/binance.py → BinanceClient.__init__` | 给容器设置 `HTTPS_PROXY` 当前无效 |
| 日期判断使用部分无时区 `datetime.now()` | `api/store/sync.py`、`api/hengpan/router.py` | 容器 UTC 默认值会影响 A 股日期，需明确上海时区 |
| Python 依赖以宽松下界为主 | `api/requirements.txt` | 每次构建可能安装不同组合，需要可复现的 Linux 依赖约束 |
| `RootModel` 和 `model_dump()` 已被使用 | `api/index.py`、`api/config.py` | 实际要求 Pydantic 2，声明 `pydantic>=1.10.0` 不准确 |
| 根健康接口只返回固定状态 | `api/index.py → root` | 能访问 `/` 不代表数据卷可写或初始化完成 |

### 需要纠正的两个直觉

1. “多人访问就加 Uvicorn workers”：这里不可行。任务 A 在 worker 1 创建，轮询落到 worker 2 会读另一个字典；同步互斥锁同样仅限本进程。
2. “Docker 开了自动重启就能恢复任务”：重启只恢复进程，不恢复 Python 内存。同步可以再次发起增量同步，但扫描不会自动接着上一只标的运行。

## 4. 方案比较与选择理由

| 方案 | 优点 | 代价 | 结论 |
| --- | --- | --- | --- |
| 单容器：FastAPI 同时提供 `dist/` | 服务数少、同源 | 要新增静态挂载、API/页面 404 顺序、缓存策略，和现有根健康接口协调 | 可行备选；当前收益不足以替代专用 Web 层 |
| 双容器：Nginx + FastAPI | 各自职责明确；前端无需运行 Node；契合现有 `/api` 代理模型 | 多一个容器和 Nginx 配置；要处理后端重新建容器后的 DNS 更新 | **推荐** |
| API + 独立任务服务 + Redis/数据库 | 可承载多进程、多副本、持久化队列 | 必须重构状态、取消、增量结果、资源锁和存储 | 当前需求不需要，延期 |

选择原则：用户要减少安装和启动步骤，并共享一个工作台，不是在要求分布式平台。Compose 可以统一管理两个服务；“一个命令”不要求“只有一个容器”。

新职责只增加生产静态服务/代理，不新增第二套业务实现。任务资源管理归 `TaskManager`，持久化仍归现有 store/history/case 模块。拒绝为 Docker 单独复制业务路由，也不增加本地/容器两套运行逻辑。

当需要多副本、服务重启后自动续跑、多个重任务长期并行且有 SLA 时，再评估外置队列及存储；不能靠调高 `--workers` 越过这个边界。

## 5. 推荐部署结构

```text
浏览器（本机或远端）
  └─ http://访问主机:8080
       └─ web：Nginx，容器端口 80
            ├─ /、/data.html、/assets/* → 前端生产产物
            └─ /api/* → http://api:18001，保留 /api 前缀
                         └─ api：FastAPI，1 worker
                              ├─ 按受控上限创建扫描子进程
                              ├─ /app/api/data → app_data 卷
                              ├─ /app/cases    → app_cases 卷
                              └─ 向外连接 Baostock / Binance
```

只发布 `web` 的一个入口端口。`api` 不配置宿主机 `ports`，不要求使用者开放 18001。Compose 内网使用服务名 `api`，不能用 web 容器内的 `localhost` 代表后端。浏览器也不能直接请求 `http://api:18001`，那是容器内部名称。[Docker Compose 网络说明](https://docs.docker.com/compose/how-tos/networking/)

场景 A/B 使用完全相同的前端产物，不需把服务器 IP 编译进 JS。首版部署在域名根路径；`/stocks/` 等前缀需要整体调整前端绝对 `/api` 路径和静态资源 base，不纳入首版。

### Compose 建议草案

以下为实施目标，**目前不能直接复制执行**：Dockerfile、健康接口和服务器并发配置尚未新增。默认无需 `.env`，仅服务器或自定义端口需要配置。

```yaml
name: hengpan

services:
  api:
    build:
      context: .
      dockerfile: deploy/api.Dockerfile
    init: true
    restart: unless-stopped
    command:
      - python
      - -m
      - uvicorn
      - api.index:app
      - --host
      - 0.0.0.0
      - --port
      - "18001"
      - --workers
      - "1"
      - --timeout-graceful-shutdown
      - "90"
    environment:
      TZ: Asia/Shanghai
      PYTHONUNBUFFERED: "1"
      PYTHONDONTWRITEBYTECODE: "1"
      OMP_NUM_THREADS: "1"
      OPENBLAS_NUM_THREADS: "1"
      MKL_NUM_THREADS: "1"
      APP_MAX_HEAVY_TASKS: "1"
      APP_MAX_WORKERS: "2"
    volumes:
      - app_data:/app/api/data
      - app_cases:/app/cases
    stop_grace_period: 120s
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:18001/api/health/ready', timeout=3).read()"]
      interval: 15s
      timeout: 5s
      retries: 4
      start_period: 30s
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  web:
    build:
      context: .
      dockerfile: deploy/web.Dockerfile
    ports:
      - "${APP_BIND:-127.0.0.1}:${APP_PORT:-8080}:80"
    depends_on:
      api:
        condition: service_healthy
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

volumes:
  app_data:
  app_cases:
```

`APP_MAX_HEAVY_TASKS`、`APP_MAX_WORKERS` 是待实现配置，不是现有变量。首版只支持全局重任务容量 1；部署校验应拒绝容量大于 1，防止误以为已经支持并行写和多路 Baostock 会话。`APP_MAX_WORKERS` 限制任务内部并行度，不改变 API worker 数。

`depends_on: service_healthy` 解决首启就绪顺序，不承担运行中故障恢复；容器处于 unhealthy 也不等于 Docker 自动重启，`restart` 主要针对退出。[Compose 启动顺序](https://docs.docker.com/compose/how-tos/startup-order/)

固定 Compose 项目名让换目录时不至于无意生成另一套卷。确需同机多实例时使用不同 `-p` 名称和端口；这是独立数据实例，不能让两个 API 挂同一套卷。

### 镜像构建要求

| 镜像 | 建议方式 |
| --- | --- |
| API | 以 Python 3.11 Debian slim 为起点，安装 CA 证书与 tzdata；工作目录 `/app`；先复制依赖锁再安装，后复制 `api/` |
| Web 构建阶段 | Node 24 LTS，`npm ci` 后 `npm run build` |
| Web 运行阶段 | Nginx 稳定版本，仅复制完整 `dist/` 与代理配置，不包含 Node 或 `node_modules` |
| 版本管理 | 验证后固定基础镜像版本/多架构 manifest digest；不使用长期漂移的 `latest` |
| API 用户 | 预创建 `/app/api/data`、`/app/cases` 并赋给固定 UID/GID，例如 10001；最终非 root 运行 |
| 构建范围 | 从本项目根目录构建，不从上层多项目目录构建 |

首版保留当前源码相对路径，用两个卷映射即可，不必先引入 `DATA_DIR` 重构。全新命名卷须实测可写；历史 bind mount 或恢复卷的 UID/GID 需由导入工具修复，不能指望命名卷自动修复任意宿主机目录权限。

Python 下界声明应至少纠正 Pydantic 2，并生成 Linux 可重现依赖锁；不要照搬本机 `pip freeze`，更不能把 macOS 虚拟环境复制进 Linux。优先 glibc slim，避免为 Alpine/musl 额外编译 numpy/pandas/scipy。依赖锁和选定镜像须分别在 `linux/amd64`、`linux/arm64` 验证；首版源码构建不强制 `platform: linux/amd64`，Apple Silicon 使用原生架构。

Node 24 是当前 LTS 候选，Node 20 已结束支持；旧 README 的“20 或更高”不应直接成为新镜像版本策略。[Node.js 官方版本表](https://nodejs.org/en/about/previous-releases)

`.dockerignore` 必须排除 `.git`、`node_modules`、`dist`、虚拟环境、`__pycache__`、`api/data`、`cases`、备份、日志、`.workflow` 和实际 `.env`，保留所需构建输入。`.gitignore` 不会替代 Docker 构建上下文过滤。

## 6. Nginx、接口和前端兼容

### 代理规则

FastAPI 已经把业务路由挂在 `/api`，代理必须保留前缀。`proxy_pass http://api:18001/` 的尾部 `/` 配合 `/api/` location 会改变路径，不能照抄。Nginx 对带 URI/不带 URI 的转发语义不同。[Nginx proxy_pass 文档](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass)

建议用 Docker DNS 动态解析，以免只重建 API 后 Nginx 继续缓存旧容器 IP。核心配置示意：

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;
    client_max_body_size 20m;

    resolver 127.0.0.11 valid=10s ipv6=off;
    set $api_origin http://api:18001;

    location ^~ /api/ {
        proxy_pass $api_origin$request_uri;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 5s;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }

    location = /index.html {
        add_header Cache-Control "no-cache";
    }
    location = /data.html {
        add_header Cache-Control "no-cache";
    }
    location ^~ /assets/ {
        try_files $uri =404;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }
    location / {
        try_files $uri $uri/ =404;
    }
}
```

此配置利用现有 hash 路由，不把不存在的 `/cases/*.json` 或 API 路径回退成 HTML。`20m` 是案例导入/保存请求体上限的初始建议值，实施时用真实完整 K 线案例测量并调整；不能把 Nginx 默认 1 MB 当成已有接口的负载上限。

目前任务进度是 HTTP 轮询和游标增量结果，不需要新增 WebSocket/SSE 配置。旧版接口和原始数据预览可能耗时，初版保留现有开发代理 600 秒量级超时；任务执行时长由后台任务负责，不应靠浏览器挂一个扫描长连接。

### 接口文档与报错

- `src/views/ApiDocsView.vue` 硬编码“后端直连 127.0.0.1:18001”，应改成当前站点 `/api` 的同源说明。
- `/api/openapi.json` 已存在，应用内“接口”页可继续使用。首版不必额外暴露 `/docs`；若承诺原始 Swagger 可访问，再完整代理 `/docs` 和其 schema 地址。
- 生产案例全部走 `/api/cases`。移除 `CaseManager.vue` 中 API 失败后访问 `/cases/index.json` 的生产回退，保留明确失败提示；开发演示代码若保留，必须限定为开发环境。
- 不为“修复案例 fallback”把案例数据卷挂到 Nginx，也不把数据库/历史快照变成静态公开目录。
- 单域部署不需要通配 CORS。Docker 正式模式关闭不必要跨域；本地开发如要前后端直连，用显式 origin 配置。CORS 不作为权限或用户认证。

## 7. 数据持久化与迁移

| 数据 | 当前位置 | Docker 位置 | 处理 |
| --- | --- | --- | --- |
| A 股行情、元数据、同步记录 | `api/data/market.db` | `app_data` 内同相对路径 | 必须持久化 |
| 加密行情、元数据、同步记录 | `api/data/crypto.db` | 同上 | 必须持久化 |
| 四类扫描历史索引与结果 | `api/data/history.db` | 同上 | 必须持久化 |
| 历史 K 线快照 | `api/data/scan_kline/` | 同上 | 必须与历史库一起备份 |
| 案例索引与正文/K 线 | `cases/index.json`、`cases/<id>/` | `app_cases` | 必须持久化 |
| 活跃任务、取消标记、流式游标 | 内存 `_tasks`、`_extras` | 不持久化 | 重启失效 |
| 浏览器主题、局部显示选项 | 浏览器 localStorage 等 | 不属于服务端卷 | 不跨浏览器自动同步 |

使用目录卷，不只挂单个 `.db`：SQLite WAL 还涉及 `-wal`、`-shm` 及临时文件。WAL 允许读写并发，但仍只有一个 writer；共享内存机制不适合把数据库放在 NFS/SMB 上给多主机共用。[SQLite WAL 官方说明](https://sqlite.org/wal.html)

命名卷与容器生命周期分离；普通 `docker compose down` 不移除这些命名卷，`down -v` 会删除本 Compose 管理的卷，属于清空数据操作，不应出现在普通升级步骤中。[Docker 卷说明](https://docs.docker.com/engine/storage/volumes/)

### 首次启动

1. 不要求使用者手工创建数据库或提前复制 `.env`。
2. API 启动初始化三个数据库、案例目录与索引，验证卷可写。
3. 空库是正常状态，页面提示先同步行情；启动和健康检查不自动全市场联网抓取。
4. 容器 ready 后启动 Web。数据源离线不妨碍读取已有行情、查看历史和案例。

### 从本地 Python 模式迁移

停止原本地后端与新 Docker API；将完整 `api/data/` 和 `cases/` 导入两个卷，修复为容器用户所有，再启动新 API。不能让两个后端同时写同一份目录，也不能只迁移行情库而漏掉历史快照和案例。

实现一套 Python 导入/导出工具，通过 `docker compose run --rm --no-deps api ...` 执行，Windows、macOS、Linux 共用，不依赖宿主机安装 sqlite3、tar 或 bash。默认拒绝覆盖非空目标，显式选择替换时先保留旧备份。

### 备份与恢复契约

首版采用短暂停机的一致备份：维护窗口停止 API，确认无其他本地进程写库，再导出两个卷为一个带清单的备份包。清单记录版本/提交、导出时间、三库与快照/案例目录、校验和。导出进程只读源卷。

不支持“边写边直接复制 `.db`”作为备份；即使 SQLite 单库在线备份有效，也没有自动解决 `history.db` 与 `scan_kline/`、案例多文件之间的一致性。本场景优先用停写降低复杂度。

恢复到空卷后，对三库运行 `PRAGMA integrity_check`，检查历史记录的 K 线文件引用、案例索引对应目录，再从页面抽查四类历史和案例。版本回滚需确认数据库兼容；涉及 schema 变化时，回到对应备份恢复，不能只换旧镜像。

## 8. 多人共享与并发控制

### 共享行为必须明示

所有访问者看到同一套行情、历史和案例；任何人都可以触发同步、维护、编辑、删除，拿到任务 ID 也能请求取消。任务 ID 只是定位标识，不代表用户所有权。页面用简短提示明确“共享工作台，操作影响所有人”，保留现有删除确认；不引入账号、认证或角色。

任务列表和忙碌状态需能被另一台浏览器发现，而不只存在发起者的组件变量里。新增轻量 `/api/tasks/active` 返回 ID、类型、状态、进度、发起时间和有效并发配置，不返回整批 K 线结果；前端可接入已有 status/cancel 接口观察和停止任务。

### 首版最小资源策略

1. 全局重任务容量 1，覆盖四类扫描、旧版联网扫描、A/加密同步、补拉及行情破坏性维护（删除、清空、cleanup、vacuum）。普通本地查询、历史查看、案例查看继续运行。
2. 在返回任务 ID 前，原子完成“占用名额 + 创建任务”，不能先 create 再等后台执行时检查，否则仍可排队堆积。
3. 忙时返回 `409` 和稳定结构：错误码、活动任务 ID/类型、可读说明；不悄悄排队，不占着 HTTP 请求等前一任务结束。
4. 所有完成、异常、取消路径通过 `finally` 释放名额；取消请求不是立即释放，必须等待实际扫描/子进程退出。任务提交后台失败也要回收。
5. 参数中的 workers/max_workers 必须校验正值及合理硬上限，并应用服务器上限；有效值取请求值与服务器上限较小者，在任务状态中回显。默认子进程上限建议 2，避免每位访问者提交一个进程池。
6. Baostock 实际使用同进程全局 socket。`/api/data/preview` 等登录/查询入口也必须使用同一资源协调机制，已有局部 `_bs_lock` 不能覆盖其他模块。纯 TCP 连通探测不登录，可独立执行。
7. 若保留原市场 `_sync_guard`，只用于业务层活动同步追踪，不再成为第二套全局任务名额来源。全局资源真值只有 `TaskManager`。

这种保守策略暂时不让本地扫描和行情同步并行，换取一致的操作边界和低资源消耗。用户仍可并发浏览，所有计算都在服务器进行。是否放开跨市场并发，必须以负载与共享资源隔离证据为前提。

### 案例写入修复

当前案例接口多为 `async def` 内直接同步文件操作，单 worker 下不应武断声称所有 HTTP 请求必然并行写坏文件；但秒级 ID 冲突即使顺序请求也会发生，直接写文件在异常退出时也有截断风险。

首版建议在现有 `case_manager` 内修复，不迁移数据库：

- 服务端生成 UUID 类唯一 ID，兼容读取旧 `case_<timestamp>` ID；外部传入 ID 需校验安全路径且禁止覆盖已有 ID。
- 统一进程内锁保护完整的读—改—写和对应文件读取，不能只锁最终 `write`。
- 单文件通过同目录临时文件 + `os.replace` 原子替换；新建先准备数据目录，再发布索引，删除先更新索引再移除目录，启动时能识别残留孤立目录。
- 多文件更新不因此变成数据库事务；承诺防半个 JSON、索引丢条和新建覆盖，不承诺异常断电下所有案例字段跨文件强原子一致。备份在停写状态进行。
- 对同一案例的顺序编辑首版采用最后一次成功保存覆盖，界面刷新后显示服务端结果；不增加协同编辑系统。

同时审查长耗时同步文件操作是否阻塞事件循环；需要时将对应路由调整到受控线程执行，并保持上述锁保护。

### 长期运行清理

`TaskManager.clean_old_tasks()` 有实现但未找到生产调用；`_extras` 也没有对应回收机制。定时清理终态任务和配套 extras，初始建议保留 1 小时；活动任务不能被清理。完成结果继续从持久化历史读取。前端收到任务 404 时停止轮询，提示任务已过期或服务已重启，转去历史页，而不是永久重试。

## 9. 退出、重启与健康检查

现有 `close_process_pool()` 是算法内部的取消/进程池清理工具，没有看到统一 FastAPI lifespan 停机协调。Uvicorn 的优雅等待、Compose 超时和 `init: true` 都不能替代应用收口。

实施要求：

- SIGTERM 后立即停止接受新重任务；对所有活动任务设置取消标记；等待后台任务退出、释放资源和落盘。
- 需要在 Uvicorn 开始等待后台任务之前触发取消，不能只把逻辑放在等待之后才执行的 lifespan teardown。实现时明确选择并验证服务启动/信号协调方式，避免直接覆盖 Uvicorn 内部信号行为。
- 90 秒 Uvicorn 优雅等待、120 秒容器停止宽限作为初始值；API 启动命令保持 exec 形式，不用吞掉信号的 shell 包装。`init: true` 负责子进程回收辅助。[Compose 服务配置](https://docs.docker.com/reference/compose-file/services/)
- 到时强停属于中断，不假报 completed。已提交行情保留；尚未完整发布的扫描历史不保证存在；下次手动增量同步恢复进度。
- 启动时识别持久化同步日志中遗留 running 状态，可转为当前日志结构支持的 failed 并说明“服务重启中断”，不要伪装任务仍活动；不从日志恢复执行线程。
- 新增 `/api/health/ready`：启动已完成、本地库可连接、数据目录具备写能力；检查快速、有界，不扫描全盘或全库。
- 不把 Baostock/Binance 是否在线放入服务健康条件。否则数据源短暂不可用会阻断本地历史浏览。

Windows/macOS 的“自动起来”还依赖 Docker Desktop/OrbStack 自身启动；Linux 依赖 Docker daemon 开机启动。Compose 的 `unless-stopped` 不会替使用者启动宿主机 Docker，也不会忽略手工停止状态。[Docker daemon 开机启动说明](https://docs.docker.com/engine/install/linux-postinstall/)

## 10. 出站网络、代理与时区

### 网络边界

浏览器只连接部署主机；行情请求由 API 容器发出。服务器访问受限时，使用者自己电脑能访问 Binance 不解决服务器同步问题。

- Baostock 使用 TCP 10030，按现有 README 和客户端实现要求允许该出站连接；不需要发布容器 10030 入站端口。
- Binance 当前基址为 `https://fapi.binance.com`，需要容器能访问相应 HTTPS 端点。
- 构建还需要访问基础镜像源、npm、PyPI；“一个命令”不代表首次完全离线启动。
- 容器里的 `127.0.0.1` 是容器自身。不能把宿主机回环代理地址原样复制给容器。

### 代理落地建议

Binance 新增可选 `BINANCE_PROXY_URL`，只作用于该客户端；缺省继续直连并保持现有本地行为，显式配置时构造对应 `ProxyHandler`。不建议直接恢复隐式读取所有环境代理，以免重新引入代码注释中记录的双重代理问题。

代理 URL 初版明确支持 urllib 可处理的 HTTP 代理（用于 HTTPS CONNECT）；不宣称原生支持 SOCKS5。访问宿主机代理时可用 `host.docker.internal`，Linux 增补 `extra_hosts: ["host.docker.internal:host-gateway"]`，且代理必须监听容器可达接口。该配置仅在需要时启用。[Compose extra_hosts](https://docs.docker.com/reference/compose-file/services/#extra_hosts)

Baostock 不通过普通 HTTP 代理，不能承诺同一个代理变量解决其 TCP 网络。两条数据通道分别在容器内验证；代理节点不可用、DNS 错误、限流、区域限制应保留可辨识错误，不无限重试。文档不把现有代码中的限额数字作为外部服务永久承诺。

### 时区

API 安装 tzdata 并设置 `TZ=Asia/Shanghai`。验证本地日期判断、A 股同步日期、历史展示与容器 UTC 环境差异。加密 K 线毫秒时间戳保持原始语义，不能为了统一时区给已经带时区的值重复加 8 小时。

## 11. 两类部署的操作体验

以下命令是实施完成后的目标流程，当前仓库尚无 Compose 文件。

### A：自己电脑使用

```bash
# 进入实际包含 package.json 和 api/ 的项目根目录
docker compose up -d
docker compose ps
```

打开 `http://localhost:8080`，首次到“数据”页同步。后续只需 Docker 在运行，容器会按 restart 策略启动；无需开两个开发终端。

修改端口用可选 `.env`：`APP_PORT=8081`。文档采用 `.env` 方式同时适配 PowerShell 和 POSIX shell，不要求用户修改前端源码。

### B：服务器多人使用

创建可选 `.env`：

```dotenv
APP_BIND=0.0.0.0
APP_PORT=8080
```

执行 `docker compose up -d`，在服务器防火墙/云安全组允许需要访问的网络到该入口；其他机器访问 `http://服务器IP:8080`。无须启动每个使用者的后端，也无须每人同步一份数据。

有现成 HTTPS 网关时，将网关指向 web 的入口。网关在宿主机运行可继续绑定回环；网关本身也是容器时，通过共享 Docker 网络连接 web，不能用其自身 localhost 指代本服务。

### 查看日志、停止与升级

```bash
docker compose logs --tail=100 api web
docker compose stop
docker compose start

# 获取新版本后，显式重建两个镜像
docker compose up -d --build
```

源码变更不会保证普通 `up -d` 自动重建已有镜像，所以首次一键启动与升级命令要分开说明。升级前确认无任务运行并备份；默认不执行 `down -v`。未来若提供预构建多架构镜像，可增加 pull 模式，但不是当前首版依赖。

## 12. 实施拆分与文件责任

下表是可直接用于后续开发的工作包；顺序不代表本轮已完成实现。

| 顺序 | 工作包 | 主要文件 | 完成证据 |
| --- | --- | --- | --- |
| 0 | 确定发布基准、校准依赖 | `api/requirements.txt`、新增锁文件、`package-lock.json` | 干净检出不缺模块；Linux amd64/arm64 安装与 import 成功 |
| 1 | 容器构建与网络 | 新增 `compose.yaml`、`.dockerignore`、`deploy/api.Dockerfile`、`deploy/web.Dockerfile`、`deploy/nginx.conf`、`.env.example` | 两服务启动，静态资源和真实 `/api` 均正常，API 重新建容器后代理恢复 |
| 2 | 初始化、健康与停机 | `api/index.py`；按需要新增独立 lifecycle 模块；`api/task_manager.py`、`api/process_pool.py` | 空卷 ready、只读卷明确失败；SIGTERM 有界退出，无遗留计算进程 |
| 3 | 共享任务资源与发现 | `api/task_manager.py`、四类扫描路由、`store/router.py`、`crypto/router.py`、`data_api.py`、前端任务提示 | 并发启动只接受一个；取消收口前仍占名额；另一浏览器可看到活动任务 |
| 4 | 案例存储加固 | `api/case_manager.py`、`api/case_api.py`、案例前端 | 同秒新增不冲突，JSON 原子替换，旧 ID 可读，无静态 fallback |
| 5 | 网络和容器 UI 适配 | `api/crypto/binance.py`、`src/views/ApiDocsView.vue`、轮询页面 | 显式代理生效，远端浏览器无 localhost API 请求，重启后旧任务轮询终止 |
| 6 | 数据迁移、备份恢复与说明 | 新增 Python 数据管理工具；README；Docker 操作指南 | 本地数据导入及新卷恢复成功，备份包含历史 K 线和案例 |
| 7 | 双场景验收 | 新增容器冒烟/并发回归、CI（若采用） | 通过下一节矩阵，记录资源数据和未覆盖平台 |

不要把 Docker 的全部配置判断塞入 750 行的 `api/index.py`；入口只负责装配，初始化/生命周期可以有单独模块。全局任务状态继续由现有 TaskManager 唯一拥有，不新增平行的“DockerTaskManager”。不借此任务整体重构算法。

工作量粗估：容器基本跑通 1–2 人日；并发、案例、退出和代理加固 2–4 人日；迁移与跨平台验收 1–2 人日，合计约 4–8 人日。此为代码审阅后的排期估算，不是已验证工时，依赖解析和数据源网络问题可能增加时间。

## 13. 验收矩阵

必须分别记录“配置语法通过”“镜像构建通过”“容器功能通过”，不能互相替代。

| 验收项 | 操作 | 通过标准 |
| --- | --- | --- |
| 干净启动 | 全新检出、无 venv/node_modules/已有卷，`docker compose up -d` | 自动构建启动；无手工建库/改源码要求 |
| 配置 | 默认和服务器 `.env` 分别运行 `docker compose config` | 默认回环、服务器全接口；只有 web 发布端口 |
| 两个前端入口 | 打开 `/`、`/data.html`、hash 页面并刷新 | JS/CSS/字体正常，无找不到资源 |
| 代理前缀 | 请求 `/api/openapi.json`、`/api/store/overview`、`/api/crypto/overview`、案例与历史 | 返回正确 JSON；未知 API 不变成 HTML |
| API 替换 | 单独强制重建 API，保持 web 不重建 | DNS 更新后代理恢复，不持续 502 |
| 空库 | 空卷启动后进入扫描与数据页 | 健康就绪，明确提示缺少行情，不自动触发全市场同步 |
| 卷完整性 | 少量同步、四类扫描保存历史、保存案例后重建服务 | 行情、history.db、历史 K 线、案例都存在 |
| 远程浏览器 | 从另一台设备访问服务器 | 网络请求指向服务器同源，无请求访问者自己的 127.0.0.1:18001 |
| 并发启动 | 两客户端同一时刻跨路由发起重任务 | 恰好一个接受，另一个 409；无孤立 pending 任务 |
| 忙时可用性 | 重任务期间多个客户端查行情、历史和案例 | 无任务串线；记录延迟、CPU、内存，无失控增长 |
| workers 边界 | 提交负数、零、超大值及超过服务器上限的有效值 | 无效输入 422；有效输入受服务器上限约束 |
| 取消与资源 | 停止同步/扫描，立即从另一浏览器再启动 | 收口前仍忙；收口后能启动；无残留子进程 |
| 案例冲突 | 同一秒创建多条、重复 ID、并发编辑/删除 | 唯一 ID，不覆盖其他案例、不产生半个 JSON；旧案例可读 |
| 任务失效 | 完成任务过 TTL、扫描期间重启 API | 旧轮询有限结束；显示过期/中断，不伪造成功；历史可查 |
| Baostock 会话 | 扫描/补拉与原始数据预览同时请求 | 不混用会话，不出现互相 logout 或串包 |
| 数据源离线 | 分别阻断 Baostock、Binance | 返回清楚错误；已有本地数据仍可用，ready 不因行情源离线失败 |
| 代理 | 容器直连及指定代理分别验证 | 客户端使用配置路径，错误可诊断；普通 HTTPS_PROXY 不被误称已支持 |
| 权限与时间 | 新卷、导入卷、只读卷、上海日期边界 | 正确 UID 可写；错误权限可定位；日期与本地模式一致 |
| 停机 | 同步及本地扫描期间分别 `docker compose stop` | 在宽限内退出；已提交数据完整，无伪 completed |
| 恢复 | 导出后恢复到全新项目名/空卷 | 三库 integrity_check=ok；历史 K 线与案例引用完整 |
| 架构 | Linux amd64、Apple Silicon arm64；Windows Docker Linux containers | 构建及冒烟通过；未跑的平台单独标注 |

功能验收优先用少量真实标的和测试夹具，避免每次验证全市场拉取。建议先用 4 vCPU、8 GB RAM、SSD 做服务器验证，2 vCPU/4 GB 只作为低并发试跑起点；这不是容量保证。数据盘空间随历史 K 线和案例增长，应测量真实任务的峰值内存与增长速度后再承诺用户数量。

资源上限需要同时控制进程池与 BLAS 线程。后续可增加 Compose CPU/内存限制，但不能仅靠 OOM kill 达成限流，也不能用限制后的“容器没退出”代替响应延迟测量。

## 14. 本轮实际验证与未验证内容

### 已完成

- 检查 Git 状态、近期提交、当前代码和基线候选；明确本地工作区与干净检出的差别。
- 扫描持久化路径、路由挂载、前端请求、后台任务、进程池、取消、代理和日期处理。
- 实际执行 `npm run build -- --outDir /tmp/hengpan-docker-research-build-20261005`，退出码 0，Vite 5.4.18 构建 735 个模块，生成 `index.html` 和 `data.html`。使用已安装依赖和 Node v24.9.0；这不是 Linux 干净 `npm ci` 验证。
- 构建仍有 Browserslist 数据较旧和大 chunk 提示；主 JS 约 1.75 MB、Material 字体约 5.4 MB，远程首次加载有优化空间，不属于 Docker 启动阻断。
- 检查本地 Python 3.11.13 的已装核心版本：FastAPI 0.141.1、Uvicorn 0.53.0、Pydantic 2.13.5、numpy 2.4.6、pandas 2.3.3、scipy 1.17.1、baostock 0.9.4。这些只是本地证据，不直接作为跨平台发布锁。
- Docker CLI 为 29.8.1，Compose 为 v5.1.2；daemon socket `/Users/macos/.orbstack/run/docker.sock` 不存在，未能连接 Docker 服务。
- 将文中的 YAML 提取到临时文件，分别用默认配置、`APP_BIND=0.0.0.0` / `APP_PORT=8081` 执行 `docker compose --project-directory <项目根目录> -f <临时文件> [--env-file <临时服务器配置>] config --format json`，两次退出码均为 0。解析结果分别为 `127.0.0.1:8080:80`、`0.0.0.0:8081:80`，API 均无宿主机端口映射。这里只证明配置草案语法和插值，不证明 Dockerfile 或容器运行可用。
- 文档结构、代码围栏、工作区索引引用检查通过，`git diff --check` 通过。
- 联网读取 Docker、Nginx、SQLite、Vite、Node 官方资料核对部署语义。搜索工具不可用，改用直接 HTTP 读取官方页面；FastAPI/Uvicorn 页面未成功读取，其相关结论以源码和待验证启动参数为依据。

### 未完成、不应宣称完成

- 未新增实际 Dockerfile/Compose，未构建或运行容器；只对文档中的 Compose 草案运行了配置解析。
- 未做 Linux 依赖解析、双架构镜像、Windows Desktop 或远程多人端到端测试。
- 未重新全量运行算法回归；本轮没有实现或修改算法。
- 未实际同步网络行情，未对外部限额、地域可用性、宿主机代理穿透作运行保证。
- 未在真实用户数据上进行恢复、压力或故障注入测试；上述验收是下一阶段要求。

研究置信度：源码结构与主要兼容障碍有直接证据；容器运行和容量结论仍待实测。研究交付完成不代表 Docker 模式已可用。

## 15. 设计自审和下一阶段边界

本轮目标是可落地研究文档，已经给出双场景入口、方案比较、数据全清单、并发契约、网络/代理、停机语义、配置草案、工作包和验收。无需通过增加认证解决共享写入问题；服务端资源控制和文件一致性仍然必要。

架构对齐：当前运行架构未改动；推荐方案保留 Vue/FastAPI 和现有 SQLite/文件存储所有权。无可用 baseline 快照，不能宣称已与一份不存在的架构基线逐项核准。正式实现后应记录单 worker/单实例、持久化路径、共享工作台和停机边界 ADR，并补齐部署基线。

保留/退出策略：保留本地开发启动、旧版算法、旧案例 ID 和原有业务 API；生产静态入口由 Nginx 承担，生产案例文件 fallback 应移除；不新增第二套任务/历史存储。明确不支持副本扩容，直到任务状态和资源协调外置且验收通过。

建议下一阶段按第 12 节实施，验收必须覆盖 A 和 B。只完成容器启动时，可称“Docker 启动链路已打通”，不能称“多人共享部署已完成”。
