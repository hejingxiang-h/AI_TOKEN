# 阶段七统一模型网关测试报告

日期为 2026-11-27。**模拟链路通过，DeepSeek 真实普通响应、SSE 和平台结算通过补测。** 初次验收使用模拟供应商。真实补测见文末。

## 实际结果

| 验证 | 环境与结果 |
| --- | --- |
| 后端集成 | 独立 PostgreSQL 16.15、启用 Lua 的 Redis 兼容服务 Garnet 与 HTTPX 模拟代理。运行 `TEST_GATEWAY_STAGE_SEVEN=1 pytest -q tests/test_gateway.py`，3 项通过，安装版代理用例在单独的进程中运行。 |
| 安装版 LiteLLM | Python 3.12.16 与 LiteLLM 1.111.0，沿用仓库的模拟供应商。运行 `TEST_GATEWAY_REAL_PROXY=1 pytest -q -k installed_proxy tests/test_gateway.py`，1 项通过。FastAPI 使用仅限该隔离环境的合成代理凭据，验证 Chat 两个别名、Messages 和 Responses 普通/流式共 8 次及 1 次 Chat 工具响应，9 条请求均结算并保留代理关联 ID。 |
| 准入与额度 | 验证无效 Key、暂停 Key、模型不在白名单、额度不足无上游调用。独立测试 Redis RPM、TPM、并发及释放后重新准入。 |
| 账务与补偿 | 验证可信用户、部门、项目与 Key 绑定。使用分片 SSE 和 Decimal 校验缓存/推理 Token 不重复计费，检查模拟供应商请求 ID。缺失 usage 经签名回调补证，重复事件保留 1 条。模拟结算提交失败后从 Redis 恢复并结算。模拟上游读超时保留预留，连接建立失败释放预留。ASGI 模拟客户端在首帧后断开时，保留部分 usage 和预算待核对。 |
| 数据库 | 独立测试库由基线升级，以及已有阶段六库升级至 `0007_gateway`；`alembic check` 无模型差异。新增 `gateway_request` 和 `gateway_event`，无既有列删除或回填。 |
| 回归 | 业务回归 `pytest -q` 7 项通过，3 个单独环境的网关测试跳过。Ruff、前端 ESLint、生产构建、Compose 配置解析通过。Windows 的原生 Redis 测试二进制未能启动，本机用 Garnet 验证协议。未联调生产 Compose。 |

`test_installed_proxy` 需要运行独立 PostgreSQL、Redis 或已验证的兼容实现，以及 [现有 PoC](poc/litellm/README.md) 的 LiteLLM 与模拟上游。仅用 `gateway_stage_seven` 测试库，通过 `APP_LITELLM_URL` 和 `APP_LITELLM_SERVICE_KEY` 提供独立环境的代理地址和凭据。

## 运行边界与后续验收

- 首版使用生效 USD 价格和 UTC 日/月窗口。适用额度规则与五级身份一起检查。TPM 以配置的模型输入上限加本次最大输出预扣，不返还窗口内的容量。务必核对每个模型别名的实际输入上限、缓存写入类型和供应商计价口径。供应商账单字段独立保留，账单导入待后续集成。
- 调用、预留、结算与告警以 PostgreSQL 记录为准。预算阈值、预留超额或不确定派发会留下事件，管理端告警投递和账单对账页面待后续接入。Redis 结算日志仅保存白名单 usage 和有限关联标识；丢失所有 usage 证据时需运营核对。
- 正式验收需要独立 LiteLLM 推理 Virtual Key、低额度授权测试 Key 与实际供应商凭据，从部署的统一 Base URL 重做 SDK 普通、流式和工具回合。验证供应商请求标识、账单计量、回调适配器跨进程投递、部署网络隔离、客户端真实断开及多副本状态。Responses 保持默认关闭，其他客户端的兼容性尚待单独验证。

开发者示例见 [GATEWAY_SDK.md](GATEWAY_SDK.md)。

## 2026-11-27 DeepSeek 真实供应商补测

使用用户提供的本地测试凭据，通过 LiteLLM 1.111.0 访问真实 `deepseek-flash`。授权上限人民币 1 元，固定短文本、单模型、每次最多 32 输出 Token，关闭自动重试。先直接经临时 LiteLLM 验证普通及 SSE，再经 FastAPI ASGI 请求、临时平台子 Key、Redis 兼容服务与独立 PostgreSQL 验证普通及 SSE。四次成功请求合计 136 输入、67 输出 Token。按高峰期未缓存输入和输出单价保守估算合计 0.000808 元，未对照供应商账单。第一次尝试因代理本地拒绝 `thinking` 参数返回 400，移除该参数后完成验证。

| 测试 | 模式 | 输入 / 输出 / 推理 | 平台费用 |
| --- | --- | --- | --- |
| 网关请求一 | JSON | 34 / 20 / 18 | USD 0.0000342 |
| 网关请求二 | SSE | 34 / 12 / 10 | USD 0.0000246 |

两次 FastAPI 调用均返回 HTTP 200，核对用户、部门、项目、Key 与结算状态正确。SSE 收到终止标记。临时平台 Key 已撤销。测试使用隔离代理的临时认证凭据及 ASGI 入口，正式 LiteLLM 服务 Virtual Key、生产部署、DeepSeek 工具调用和供应商账单仍待验收。 [DeepSeek 官方费率](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)
