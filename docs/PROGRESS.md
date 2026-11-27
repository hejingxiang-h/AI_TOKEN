# AI Token Gateway 开发进度

更新日期 2026-11-27

## 当前状态

- 需求分析与技术架构已确认，详见 [需求规格](01-requirements.md) 和 [技术架构](03-architecture.md)。
- 项目开发规范与进度记录已建立，详见 [AGENTS.md](../AGENTS.md)。
- 详细架构和数据库设计已完成，模拟协议探针 10 项通过。Windows 本机 Prisma 数据库连接和 Virtual Key 查询已通过专项回归，结果见 [PoC 运行记录](poc/litellm/RESULTS.md)。

- 阶段四基础工程已初始化，已完成本机基础验收，正式 Redis 运行待复测。

## 阶段进度

| 阶段 | 状态 | 当前成果或进入条件 |
| --- | --- | --- |
| 需求与调研 | 已完成 | [需求与技术评审文档](README.md) 已交付，需求与架构已获确认。 |
| 技术 PoC | 部分通过 | 模拟协议 10 项通过。本机 Prisma 连接专项五项通过。Key 生命周期、限额、真实供应商与目标部署待验证。 |
| 阶段四 工程初始化 | 待验收 | FastAPI、Vue、Alembic 和独立的 Compose 基础工程。 |
| 阶段六 基础管理与鉴权 | 部分通过 | 真实业务 API 与管理页已接通，LiteLLM Key 写入与网关额度待验证。 |
| 阶段七 网关、账务与运营面板 | DeepSeek 真实链路部分通过 | 已验证 JSON、SSE 和平台结算，正式部署与真实工具调用待验收。 |
| 内部试点与上线 | 未开始 | 按验收方案收集证据并完成试点验收。 |

## 任务记录

### 2026-11-27 项目开发规范与进度记录

| 汇报项 | 本次记录 |
| --- | --- |
| 完成内容 | 编写全项目开发规范与初始阶段记录。 |
| 修改文件 | 项目根目录的 `AGENTS.md` 和 `docs/PROGRESS.md`。 |
| 数据库变化 | 无。 |
| 测试命令和结果 | 本次为文档任务，未执行 Ruff、Pytest 和 Playwright。 |
| 未完成事项 | 技术 PoC 和实际供应商调用验证待启动。 |
| 手动验证方法 | 打开两个新增文件，核对规范、汇报字段、阶段状态及相对链接。 |
| 下一阶段建议 | 进入技术 PoC 时，按接入矩阵和验收方案验证 OpenAI 与 DeepSeek 的 Chat Completions，以及 Anthropic Claude 的 Messages。 |

### 2026-11-27 系统架构、数据库设计与 LiteLLM PoC

| 汇报项 | 本次记录 |
| --- | --- |
| 完成内容 | 交付详细架构、ER 图、API、权限、模型接入、安全和阶段计划。固定 LiteLLM 1.111.0 的模拟协议探针通过 10 项。 |
| 修改文件 | `ARCHITECTURE.md`、`DATABASE.md`、`API.md`、`PERMISSIONS.md`、`MODEL_INTEGRATION.md`、`SECURITY.md`、`DEVELOPMENT_PLAN.md`、`PROGRESS.md` 及 `poc/litellm/`。 |
| 数据库变化 | 未改业务库，未创建业务 Alembic 迁移。仅在隔离 PostgreSQL 执行 LiteLLM 自身迁移。 |
| 测试命令和结果 | `python run_native.py --logs <临时日志目录> --protocol-only --startup-timeout 150` 通过 10 项，跳过 3 项。数据库模式未通过本机运行验证。Ruff 与 Compose 静态配置校验通过。 |
| 未完成事项 | 数据库相关的 Key、白名单和限额用例待在官方镜像中复测。真实供应商、目标 Docker、Redis 多实例和生产回调安全仍待验证。 |
| 手动验证方法 | 按 [PoC 说明](poc/litellm/README.md) 运行，核对 [运行记录](poc/litellm/RESULTS.md) 的逐项状态。 |
| 下一阶段建议 | 评审详细设计和 PoC 证据，在目标环境完成真实供应商及多实例验证。完整业务实现等待确认。 |

### 2026-11-27 Prisma 连接诊断及回归

| 汇报项 | 本次记录 |
| --- | --- |
| 完成内容 | 定位旧日志里的 Windows 控制台中断及 PostgreSQL 停止。隔离启动后完成 PostgreSQL、Prisma、LiteLLM 数据库连接、Virtual Key 列表及临时表读写五项回归。 |
| 修改文件 | 更新 `PROGRESS.md` 和 `poc/litellm/RESULTS.md`。诊断脚本与日志保留在工作区临时运行目录。 |
| 数据库变化 | 无持久数据与 Schema 变化。仅写读并清理会话临时表。252 条代理迁移与当前包匹配。 |
| 测试命令和结果 | `fix_diagnostic_authorized.py`、`fix_proxy_ab.py`、`fix_validation.py` 退出码均为 0。逐条命令与结果见 [Prisma 连接专项复查](poc/litellm/RESULTS.md#prisma-连接专项复查)。 |
| 未完成事项 | 无本机连接回归遗留。旧中断发送方未识别。Docker 引擎和前阶段的 Key 生命周期及限额场景待单独测试。 |
| 手动验证方法 | 参照专项记录，以隔离实例分别执行 `pg_isready`、Prisma 查询、LiteLLM `/health/readiness` 和 `/key/list`。 |
| 下一阶段建议 | 保留现有依赖与配置，等待确认。本阶段停留在 Prisma 连接排查。 |

### 2026-11-27 阶段四 基础工程初始化

| 汇报项 | 本次记录 |
| --- | --- |
| 完成内容 | 建立 FastAPI 基础工程、Vue 系统健康页、独立 Compose、PostgreSQL 初始化脚本、Redis ACL、LiteLLM 和 Nginx 配置。 |
| 修改文件 | 根目录 README、环境样例与 Compose，新增 backend、frontend 和 deploy，更新开发计划和进度。八份 PoC 文件 SHA-256 均与任务开始时相同。 |
| 数据库变化 | 在独立 PostgreSQL 16.15 测试库执行基线 `0001_initial_baseline`。在临时目录生成测试迁移，验证建表、降级和清理。未对 PoC 库执行迁移。 |
| 测试命令和结果 | Python 3.12.16 下 uv 同步并生成锁文件。Ruff 通过，Pytest 3 项通过。FastAPI、Swagger、OpenAPI、PostgreSQL 和 Alembic 启停实测通过。Redis 不可用时就绪 503、存活 200。 |
| 前端和部署 | Node 22.23.5 下 npm 安装、ESLint、Prettier 和生产构建通过。Chromium 实测 Vite 开发端和生产预览，路由、渲染、ECharts、Axios 首次和刷新请求通过。Compose 配置通过，未进行完整容器联调。 |
| 未完成事项 | Windows 本机无法启动所试 Redis 移植版。Garnet 兼容服务的真实 TCP 连接返回就绪 200，正式 Redis 7.4 镜像运行待目标环境复测。LiteLLM Key 生命周期、白名单、Budget 和 RPM 仍待前阶段专项验证。 |
| 手动验证方法 | 参照 [根目录 README](../README.md)，分别访问 Swagger、三个健康检查路径和系统健康页，对照 HTTP 状态。 |
| 下一阶段建议 | 等待本阶段验收。 |

### 2026-11-27 PC 管理后台

| 汇报项 | 本次记录 |
| --- | --- |
| 完成内容 | 实现登录、工作台、Token 统计和 11 个管理入口，及统一的布局、表格、图表、表单和确认弹窗。所有模拟页面标明数据来源。 |
| 修改文件 | `frontend/src` 的视图、路由、公共组件、样式和模拟数据模块，以及本进度文档。 |
| 数据库变化 | 无。演示记录存于浏览器，登录只记录会话用户名。 |
| 测试命令和结果 | `npm run lint` 和 `npm run build` 通过。使用 Playwright Chromium 验证生产预览的 14 个入口、1280 / 1440 / 1920 布局、图表、时间筛选、分页、用户新增编辑删除、详情、校验、空结果与本地存储错误恢复。控制台无错误。 |
| 未完成事项 | 真实认证与业务 API 尚未接入。ECharts 构建分包约 556 kB，Vite 给出体积提示。GitHub 远程尚未配置，等待用户确认推送。 |
| 手动验证方法 | 在前端目录运行 `npm run dev`，使用演示身份登录，检查工作台时间范围及用户管理增删改查。 |
| 下一阶段建议 | 确认 GitHub 仓库和推送范围后再推送。 |

### 2026-11-27 阶段六基础业务

| 汇报项 | 本次记录 |
| --- | --- |
| 完成内容 | 登录与会话、数据范围、组织和项目、模型目录与价格、子 Key 本地生命周期、配额规则，以及七个真实数据管理页。 |
| 修改文件 | 后端 `app/api`、`app/core`、`app/models`、`app/repositories`、`app/services`、`app/schemas`、`app/integrations`、`app/tasks` 与测试。前端 API、登录、路由、会话和管理视图。根目录 Compose、环境样例和 README。 |
| 数据库变化 | 新增 `0002_auth` 至 `0006_access`，涵盖账户、会话、角色、组织、项目、审计、模型目录、价格版本、Key 和配额。仅对独立测试库执行迁移。 |
| 测试命令和结果 | `ruff check app migrations tests` 通过。独立 PostgreSQL 执行 `alembic downgrade 0003_permissions`、`alembic upgrade head`、`alembic check` 通过，`pytest -q` 6 项通过。前端 lint、生产构建与 Compose 配置检查通过。Playwright Chromium 使用真实 FastAPI 和 PostgreSQL 验证登录、七个管理页、部门新增、搜索、详情、页面刷新后恢复会话和退出，未捕获未处理的页面异常。 |
| 未完成事项 | LiteLLM Virtual Key 写入及对账，真实供应商连通，真实模型请求更新最后使用时间，配额执行及预警，统计与导出。 |
| 手动验证方法 | 按 [根目录 README](../README.md) 初始化超级管理员，登录并分别用普通用户和主管检查列表与详情范围。管理员创建组织、项目和 Key 授权，由所有者领取一次。 |
| 下一阶段建议 | 在隔离的 LiteLLM 实例完成写接口和生命周期验证，再接入同步与网关配额控制。 |


### 2026-11-27 LiteLLM 子 Key 同步架构检查

| 汇报项 | 本次记录 |
| --- | --- |
| 完成内容 | 核对本机 LiteLLM 1.111.0 OpenAPI、源码与当前业务签发链路，确认当前缺少远端编排和推理转发。 |
| 修改文件 | [子 Key 同步架构检查](poc/litellm/KEY_SYNC_ANALYSIS.md) 和本进度记录。 |
| 数据库变化 | 无。 |
| 测试命令和结果 | Python 3.12.16 通过 `importlib.metadata.version("litellm")` 输出 1.111.0，`app.openapi()` 输出七条 Key 管理操作及请求 Schema。未执行写入和推理测试。 |
| 未完成事项 | 隔离环境的 Key 生命周期、缓存传播、预算和速率限制运行验证，及 FastAPI 推理准入实施。 |
| 手动验证方法 | 在项目 PoC 虚拟环境中调用 LiteLLM 的 `app.openapi()`，按分析文档检查接口和参数。 |
| 下一阶段建议 | 确认是否维持 FastAPI 准入与私网服务 Key 模式，或引入逐 Key 远端映射。 |


### 2026-11-27 阶段七网关架构确认

| 汇报项 | 本次记录 |
| --- | --- |
| 完成内容 | 确认 FastAPI 统一鉴权和代理，采用私网 LiteLLM 服务 Virtual Key，明确业务状态、metadata、配额与 usage。 |
| 修改文件 | ARCHITECTURE.md、MODEL_INTEGRATION.md、本进度及 [架构决策](poc/litellm/GATEWAY_ARCHITECTURE_DECISION.md)。 |
| 数据库变化 | 无。实施若需变更，先提交兼容迁移方案。 |
| 测试命令和结果 | 用 `rg`、`Get-Content` 核对项目路由、Key 状态、安装版关联头和 metadata 处理；仅执行文档验证。 |
| 未完成事项 | FastAPI 推理入口、限流、预算预留、SSE、结算；LiteLLM metadata/log/callback 和上游隔离的运行验证。 |
| 手动验证方法 | 按决策文档的验收项在隔离环境逐协议联调。 |
| 下一阶段建议 | 先实现准入、凭据隔离和模拟上游转发，再加入额度和结算。 |

### 2026-11-27 后端提交与安全检查

| 汇报项 | 本次记录 |
| --- | --- |
| 完成内容 | 后端与 README、安全设计文档提交并推送 GitHub main。 |
| 修改文件 | 后端应用、迁移、测试、README.md 和 SECURITY.md。提交为 `78d98bf`。其余改动保留在工作区。 |
| 数据库变化 | 本次未执行数据库结构变更。 |
| 测试命令和结果 | Ruff、`alembic check`、PostgreSQL 集成环境下 `pytest -q` 通过，6 项测试通过。暂存区 39 个文件通过范围、凭据模式和差异检查，唯一命中为合成测试口令。 |
| 未完成事项 | 阶段七推理与端到端供应商验证待实施。 |
| 手动验证方法 | 在远端 main 核对提交文件列表，在独立测试库运行迁移与后端测试。 |
| 下一阶段建议 | 按阶段七决策推进推理准入。 |

### 2026-11-27 阶段七统一模型网关

| 汇报项 | 本次记录 |
| --- | --- |
| 完成内容 | 实现子 Key 准入、模型授权、Redis 限制、五级预算、LiteLLM JSON/SSE、用量和结算、调用事件与恢复。 |
| 修改文件 | 后端网关 API、服务、集成、数据库模型与测试，增加 LiteLLM 回调适配器和部署配置。更新前端 Key 状态与 SDK、验收文档。 |
| 数据库变化 | 新增 `0007_gateway`，仅在独立测试库验证。增加调用及事件表。 |
| 测试命令和结果 | Ruff、Alembic、7 项业务回归、3 项模拟网关测试、1 项安装版 LiteLLM 模拟供应商测试、前端 lint/构建及 Compose 解析通过。 |
| 未完成事项 | 低额度真实供应商验收、标准 Redis 和 Compose 联调、代理回调跨进程投递、运营展示与供应商账单导入。 |
| 手动验证方法 | 见 [SDK 调用](GATEWAY_SDK.md) 和 [验收报告](GATEWAY_TEST_REPORT.md)。 |
| 下一阶段建议 | 用单模型、低额度授权完成真实供应商验收，然后开放目标客户端。 |

2026-11-27 补测通过 DeepSeek 真实普通与流式调用，已核对用量、归属及结算。仅使用隔离环境，未变更数据库结构。详见 [验收报告](GATEWAY_TEST_REPORT.md)。

2026-11-27 发布前审查覆盖网关、前端接入、部署和文档。环境文件与私有运行日志留在本机，公开验收报告移除真实请求标识。

## 更新规则

每次任务结束时更新当前状态和阶段进度，在任务记录中追加日期、任务名称及七项汇报内容。历史记录保留。仅在取得相应验证证据后更新测试结果及阶段完成状态。
