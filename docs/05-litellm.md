# LiteLLM 开源版与商业版能力差异

首版采用 LiteLLM OSS 作为私网模型代理的方案进入 PoC。业务平台自行实现公司身份、部门范围、项目授权、审计和用量账本。LiteLLM 商业能力以目标镜像的版本、许可和报价确认结果为准。官方资料核对日期为 2026-11-27。

| 能力 | 开源版基线 | 商业版及条件 | 本项目处理 |
| --- | --- | --- | --- |
| 许可证与部署 | 仓库根许可证为 MIT，按组件和固定镜像核对许可。可自托管。 | 官方文档说明同一镜像可用许可密钥启用相应能力；商业条款及支持视合同。 | 固定稳定版本和摘要，检查附带许可证与启用的功能。 [仓库许可](https://github.com/BerriAI/litellm/blob/main/LICENSE) · [Enterprise](https://docs.litellm.ai/docs/enterprise) |
| 协议、供应商和代理 | 模型路由、常见协议、流式和工具代理。转换细节取决于模型和路由。 | 企业许可包含额外治理和运维选项。 | 只暴露经测试的路由。 [支持的接口](https://docs.litellm.ai/docs/supported_endpoints) |
| 虚拟 Key、基础限额和用量 | 文档列出虚拟 Key、模型范围、用量与基础额度和限流。Redis 协调和降级设置须按版本验。 | 官方列出按标签配额、Key 内模型级费用额度、临时提额和软额度邮件等。 | LiteLLM Key 仅供私网。平台的项目及 Key 费用额度独立执行。 [虚拟 Key](https://docs.litellm.ai/docs/proxy/virtual_keys) · [额度与限流](https://docs.litellm.ai/docs/proxy/users) · [企业能力](https://docs.litellm.ai/docs/enterprise) |
| 平台身份和管理权限 | 基础内置管理与团队能力。账号、团队角色和授权范围按版本核查。 | 官方列出更细粒度 RBAC、组织、团队管理员、企业 IdP JWT 和 SSO。UI SSO 文档列出最多 5 用户的免费条件。 | 平台 JWT 和部门权限独立实现。首版不依赖 LiteLLM SSO。 [从 OSS 迁移](https://docs.litellm.ai/docs/enterprise/moving_from_oss) · [许可条件](https://docs.litellm.ai/docs/enterprise/activate) |
| 项目级治理 | 基础团队和 Key 可用于归集。 | 官方项目管理页面标明需要 Enterprise，包含项目预算、速率和模型权限。 | 用业务库维护企业项目及权限，验证采购对未来治理的价值。 [项目管理](https://docs.litellm.ai/docs/proxy/ui_project_management) |
| 调用日志和管理审计 | 代理用量和调用日志，持久化及回调可能异步。 | 管理操作审计和保留策略、团队级日志和部分导出集成。 | 业务调用记录、管理审计、内容风险证据分别实现。 [请求生命周期](https://docs.litellm.ai/docs/proxy/architecture) · [企业审计与日志](https://docs.litellm.ai/docs/enterprise) |
| 内容防护与日志脱敏 | 官方列出 OSS 自定义 guardrail 机制和 Presidio；具体集成与配置需实测。 | 官方列出部分内建 guardrail、按团队或 Key 设置的治理。 | 首版实现有限的规则检测和脱敏。验证 spend logs、回调、遥测各自配置。 [Guardrail 许可](https://docs.litellm.ai/docs/enterprise) · [日志配置](https://docs.litellm.ai/docs/proxy/ui_logs) |
| 密钥与运维支持 | 私网部署、部署侧管理凭据、社区支持。 | 官方列出原生 Secret Manager 集成、自动轮换、部分网络访问控制和商业支持选项。 | 首版采用部署侧凭据和平台自有轮换，保留采购评估。 [企业能力与支持](https://docs.litellm.ai/docs/enterprise) |

## 版本验证及采购门槛

- 在未配置许可证的固定镜像上用隔离 PostgreSQL 和 Redis 验证三条路由、服务 Key、模型白名单、请求标识和日志脱敏。鉴权、统计、审计与配额的 P0 验收不依赖 Enterprise 开关。
- 用受控账务样本检查终止用量和上游请求 ID 在响应、代理日志和账本之间的关联。测试同一镜像下异步日志积压、代理重启、回调失败和落库重复。
- 若未来需要外部 IdP、团队自管、集成密钥系统、合规审计或 SLA，用试用许可验证目标功能、免费条件、合同主体、支持窗口、日志留存和数据流向。取得书面授权和报价后再决定采购。
