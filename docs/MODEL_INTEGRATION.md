# 模型接入与 LiteLLM PoC

核对日期为 2026-11-27。GitHub 最新正式发布和 PyPI 均指向 **LiteLLM 1.111.0**。PoC 固定该版本，使用本地合成模型服务、合成 Key 和无商业许可证的进程。所有真实供应商、合同价目、区域网络和客户端生产配置仍待验证。 [正式发布](https://github.com/BerriAI/litellm/releases/tag/v1.111.0) · [PyPI 版本](https://pypi.org/project/litellm/1.111.0/)

## 能力矩阵

| 能力 | 官方证据和许可 | 验证条件及边界 |
| --- | --- | --- |
| Virtual Key | 开源版文档提供生成、查询和模型范围。 [Virtual Keys](https://docs.litellm.ai/docs/proxy/virtual_keys) | 使用专用 PostgreSQL，生成并用新 Key 调用。平台开发者 Key 与代理内部 Key 独立。 |
| 禁用、恢复和撤销 | 文档和固定版本代码列 `/key/block`、`/key/unblock`、`/key/delete`。 [Virtual Keys](https://docs.litellm.ai/docs/proxy/virtual_keys) · [1.111.0 路由源码](https://github.com/BerriAI/litellm/blob/v1.111.0/litellm/proxy/management_endpoints/key_management_endpoints.py) | 验证新请求拒绝、恢复和删除后失效。多副本传播与在途取消另测。 |
| 模型白名单 | Virtual Key 具有允许模型列表。 [Virtual Keys](https://docs.litellm.ai/docs/proxy/virtual_keys) | 检查允许模型和禁止模型。平台空列表策略恒拒绝。 |
| 预算与限速 | 文档列 Key 预算、预算窗口、RPM、TPM 和并发控制。 [预算与速率](https://docs.litellm.ai/docs/proxy/users) | 执行 Key 月度类预算与 RPM 测试。分布式 Redis、故障策略和企业预算硬上限单独验收。 |
| Chat Completions | 开源代理文档列出接口。 [网关接口](https://docs.litellm.ai/docs/supported_endpoints) | OpenAI、DeepSeek 两条路由，JSON、SSE、usage。 |
| Responses API | 代理文档列出接口和翻译路径。 [网关接口](https://docs.litellm.ai/docs/supported_endpoints) | OpenAI JSON/SSE，核对终态 usage。Codex 与状态续接另测。 |
| Anthropic Messages | 代理文档列出 `/v1/messages`。 [网关接口](https://docs.litellm.ai/docs/supported_endpoints) | Claude JSON/SSE 和缓存字段，原生与转换行为按固定版本验证。 |
| 流式响应 | 文档列出三种协议的流式模式。 [网关接口](https://docs.litellm.ai/docs/supported_endpoints) | 覆盖三种终止语义。网络中断、取消、边收边发延迟由下一轮压测。 |
| 工具调用 | 文档列出工具调用，模型与转换路径的参数覆盖不同。 [工具调用](https://docs.litellm.ai/docs/completion/function_call) | 探针覆盖 Chat 非流式函数调用及结果回传，其他协议与流式工具分片另测。 |
| usage 回传 | 供应商协议规定位置和字段。 [OpenAI Chat](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) · [OpenAI Responses](https://developers.openai.com/api/reference/resources/responses/methods/create) · [DeepSeek Chat](https://api-docs.deepseek.com/api/create-chat-completion/) · [Anthropic SSE](https://platform.claude.com/docs/en/build-with-claude/streaming) | Chat 核对最终 usage，Responses 核对终态，Anthropic 检查消息开始、增量和缓存。缺失字段保留待核对。 |
| 调用事件回调 | 代理支持自定义日志钩子，Generic API 支持目标和请求头配置。 [代理日志](https://docs.litellm.ai/docs/proxy/logging) · [Generic API](https://docs.litellm.ai/docs/observability/generic_api) | PoC 验证 success/failure hook 与脱敏字段送达。应用层签名、持久重投和账务核对由平台实现。 |

## 开源版、商业版和平台自研

| 来源 | 范围 |
| --- | --- |
| LiteLLM 开源版 | 本项目选用三协议代理、供应商认证、内部 Virtual Key、基础白名单和限额、自定义日志回调。依照固定版本实测。 [OSS 迁移说明](https://docs.litellm.ai/docs/enterprise/moving_from_oss) |
| LiteLLM 商业版 | 官方列出企业项目治理、细粒度组织角色、管理审计、企业 SSO/JWT、额外密钥管理和运维支持。UI SSO 有官方所述免费人数条件。具体以许可与版本为准。 [Enterprise](https://docs.litellm.ai/docs/enterprise) · [许可条件](https://docs.litellm.ai/docs/enterprise/activate) |
| 平台自研 | 企业角色和数据范围、开发者 Key、项目和 Key 原子预算、归因、用量归一化、费率版本、账本、审计、告警及签名回调补偿。 [系统架构](ARCHITECTURE.md) |

## PoC 复现与证据

可复现材料位于 [PoC 说明](poc/litellm/README.md)，包含模拟上游、轻量回调适配器、协议与 Key 探针及 Compose 配置。正式结果以 [运行记录](poc/litellm/RESULTS.md) 为准。仅适用于本地无真实 Key 的测试。已观察到三类协议的 JSON 和 SSE、用量回传、Chat 工具回合以及成功和失败事件送达。数据库相关的 Virtual Key 生命周期、白名单、预算和 RPM 有官方依据，未通过本机运行验证。

## 真实供应商后续验证

- 用企业授权凭据，从实际上线网段验证 OpenAI Chat、DeepSeek Chat 和 Anthropic Messages。逐路由覆盖 JSON、流式、工具、异常与中断，对比提供方原始 usage、请求标识、缓存计价与账单。
- 校验终态用量缺失、上下游取消、重复回调、路由参数、Anthropic 版本头和工具能力。验证代理调用标识是否能稳定与应用请求 ID 一对一关联。
- 固定实际运行镜像摘要，确认 Redis 多实例后的 Key 变更传播、限流协调、故障拒绝策略和版本升级回归。Responses 及 Codex 另经版本发布审批。
