# 阶段十全系统测试与安全审查

日期为 2026-11-27。范围为阶段九提交及本轮安全修复。使用隔离 PostgreSQL、Redis 兼容服务、合成身份与测试授权。未改动生产数据库，已验证的 LiteLLM PoC 配置未改动。

## 后端和部署

| 检查 | 实际命令与结果 |
| --- | --- |
| 认证和组织权限 | 在独立 PostgreSQL 上执行 `pytest tests/test_auth_integration.py tests/test_organization_integration.py tests/test_permissions.py tests/test_health.py -q`，6 项通过。覆盖登录、刷新、退出、改密、停用、三类角色以及跨部门和跨项目数据权限。 |
| 推理、额度和计量 | 启用 `TEST_GATEWAY_STAGE_SEVEN=1` 运行 `pytest tests/test_gateway.py -q`，3 项通过，安装版代理用例在该进程跳过。含子 Key 拒绝、暂停、白名单、额度、RPM/TPM/并发、两笔并行请求抢同一笔预算、截断和断开、费用、幂等回调及失败恢复。该套件使用模拟代理。 |
| 审计告警、统计 | 启用隔离集成环境，分别执行 `pytest tests/test_risk.py -q` 和 `pytest tests/test_usage.py -q`，各 2 项通过。核对告警去重、状态流转、只向管理员展示来源 IP、日志脱敏及角色范围。 |
| 迁移与任务进程 | 隔离库 `alembic upgrade head` 与 `alembic check` 通过，head 为 `0008_risk`。独立 worker 在隔离数据库与 Garnet 上执行 `python -m app.tasks.risk_worker --once`，退出码 0。 |
| 备份恢复 | 使用 `pg_dump -Fc` 导出合成数据，`pg_restore --exit-on-error --no-owner` 恢复到新的隔离库。源与目标迁移版本、调用、告警、审计行数一致。 |
| Docker | `docker compose --env-file .env.example config --quiet` 通过。`docker desktop start --timeout 35` 超时，`docker version` 仍无 Linux 引擎。未执行完整容器部署、容器重启或卷持久化验证。 |

## 前端 Playwright

Win11 上启动原生 FastAPI 和 Vite 生产预览，连接隔离 PostgreSQL，运行 Chromium。管理员及普通用户登录、退出和菜单路由通过。验证用户创建、必填表单、编辑、停用、筛选、翻页及角色限制。含 HTML 的合成显示名作为文本展示，未生成对应 DOM 元素。统计验证时间筛选、Token 图表、空状态和注入的 HTTP 503 重试。1280、1440、1920 宽度检查未发现页面横向溢出。ESLint、`npm run build` 通过。

## 安全检查及修复

| 项目 | 证据和处置 |
| --- | --- |
| 推理媒体边界和 SSRF | 修复前仅校验顶层参数，内部内容块仍可能交给供应商适配器解析外部媒体。现限定已支持的文本及客户端执行工具内容，拒绝媒体与文件引用。模拟用例确认 400 且代理收到 0 次请求。固定代理目标和禁用跳转经过代码检查。生产网络出口策略仍需实测。 |
| Compose 出站 | 原 LiteLLM 服务只连接内部网络。本轮为代理添加单独的供应商出站网络，代理仍无公开端口。Compose 解析通过，容器实际连通待验收。 |
| SQL 注入、越权和 IDOR | 检查 PostgreSQL 动态条件使用 SQLAlchemy/绑定参数，无客户端字符串拼接生成查询。授权负例由组织、统计和审计集成测试覆盖，范围外对象返回 404，管理操作限制角色。未做专用 DAST。 |
| JWT、回调与权限缓存 | 检查 JWT 签名算法、颁发者、受众、有效期及会话撤销。测试拒绝缺签名回调及重复回调不重复结算。时间窗与签名比较经代码检查。统计接口以权限过滤并发送 private/no-store，当前没有共享统计缓存。 |
| 密钥与日志 | 检查本地真实凭据并扫描 176 个已跟踪路径。无精确匹配，真实环境文件仍被 Git 忽略。审计测试验证敏感字段与合成凭据不写摘要。没做生产日志、备份和 APM 的全链路脱敏探针。 |
| 依赖 | `npm audit --registry=https://registry.npmjs.org --json` 及其 `--omit=dev` 结果均 0 项。官方 OSV 批量查询检查 Python 锁定生产依赖加 LiteLLM 固定版本，共 37 项，结果 0。未扫描容器基础镜像和镜像内全部依赖。 |
| 管理接口 | 静态核对 Nginx 的内部和代理管理路径拒绝规则，以及 Compose 无代理端口发布。Docker 不可用，本次没有验证容器网络实际路径。 |

## 真实供应商复测

本机 LiteLLM 1.111.0 经授权 DeepSeek 测试 Key 验证三次 `deepseek-flash`。普通和 SSE 均 HTTP 200，SSE 收到终止标记并回传 usage。工具用例 HTTP 200 且收到预期函数调用，由客户端处理，本轮未执行外部工具。三次共 374 输入、96 输出 Token。按官方高峰未缓存口径估算 0.001516 元人民币，低于已授权的 1 元预算。该金额为费率估算。上述三次为代理复测。随后使用临时平台子 Key，经 FastAPI、LiteLLM 与真实 DeepSeek 再执行普通和 SSE，两次均 HTTP 200，账本结算分别为 USD 0.0000234 和 USD 0.0000294，用户、部门、项目和 Key 归属一致。两次合计 68 输入、27 输出。阶段十共 5 次成功真实请求，按同一高峰费率保守估算共 0.001868 元人民币。 [DeepSeek 官方费率](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

真实 DeepSeek 超时和断流未主动触发，相关处理以模拟网关测试为证。OpenAI 和 Claude 没有本轮授权的低额度测试 Key，因此未执行真实调用。

## 上线条件

上线前需在目标环境完成 Docker 部署和重启、持久卷、可信代理、管理接口隔离和供应商出站实测。还需复核代理的实际计费输入上限与平台预留一致、配置登录入口限速、执行容器镜像扫描、完成账单对账和生产日志脱敏验证。按供应商单独补齐真实工具回合、超时及中断测试，再对外声明兼容范围。

DeepSeek 的受限服务 Virtual Key、TCP 统一入口、普通、SSE、完整工具回合与账本补测已通过。见 [DeepSeek 全链路补测](DEEPSEEK_ACCEPTANCE.md)。
