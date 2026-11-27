# 模型和客户端接入可行性分析

官方资料核对日期为 2026-11-27。下表中的“有文档”表示官方资料列出能力。V1.0 三条路由均需在目标账户、模型和固定版本组合上通过真实调用验收。每项验证记录客户端版本、企业套餐、模型、协议、LiteLLM 镜像摘要、测试日期和脱敏证据。

## 模型 API 供应商

| 供应商及凭据 | Chat Completions | Responses API | Anthropic Messages | 流式与工具 | 平台计划及证据 |
| --- | --- | --- | --- | --- | --- |
| OpenAI API，公司 API 项目密钥 | 有文档 | 有文档，状态续接和工具按模型验证 | 原生接入未纳入；LiteLLM 转换另测 | SSE 和函数工具有文档，按模型与接口确认 | P0 Chat；P1 Responses 和 Codex。 [Chat API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) · [Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create) |
| DeepSeek API，企业授权 API Key | 有文档 | 有文档，部分参数有固定值或限制 | 有文档，独立 Base URL | 三种接口的流式和工具语义按协议及模型验证，终止事件各异 | P0 Chat；另外两种协议候选。 [Chat API](https://api-docs.deepseek.com/api/create-chat-completion/) · [Responses 指南](https://api-docs.deepseek.com/guides/responses_api/) · [Messages 指南](https://api-docs.deepseek.com/guides/anthropic_api/) |
| Anthropic API，Claude 企业授权 API Key | 原生接入未纳入；LiteLLM 转换另测 | 原生接入未纳入；LiteLLM 转换另测 | 有文档 | SSE、工具调用及缓存用量有文档，按模型和版本头验证 | P0 Messages。 [Messages API](https://platform.claude.com/docs/en/api/messages/create) · [流式协议](https://platform.claude.com/docs/en/build-with-claude/streaming) · [缓存](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) |
| Google Gemini API，Gemini API Key | 有 OpenAI 兼容接口 | OpenAI 兼容入口的 Responses 支持待验证 | 原生接入未纳入 | Chat 兼容文档列出流式和函数调用，字段覆盖按模型测试 | P1 候选，先选 Gemini Developer API，企业采用其他 Google 部署时另立验证。 [Gemini OpenAI 兼容](https://aistudio.google.com/docs/openai) |
| 火山方舟豆包，公司方舟凭据 | 有文档 | 有文档，模型覆盖和参数依推理端点 | 待验证，本期候选使用前两者 | 流式和工具以具体方舟模型、端点和 API 能力为准 | P1 候选，核验模型标识、区域地址、缓存和计费。 [Chat API](https://docs.volcengine.com/docs/ark/chat-api?lang=zh&redirect=1) · [Responses 迁移](https://console.volcengine.com/ark/region%3Acn-beijing/docs/responses-api-migration) · [Responses 接口](https://console.volcengine.com/ark/region%3Acn-beijing/docs/create-model-responses-api) |
| Grok API，公司授权 API Key | 有 OpenAI 兼容接口 | 有文档，官方将其作为新接入方向 | 原生接入未纳入 | 文档列出流式，工具类型及能力依模型和协议 | P1 候选，核验企业账号、区域与价格。 [Chat API](https://docs.x.ai/developers/rest-api-reference/inference/chat-completions) · [Responses API](https://docs.x.ai/developers/rest-api-reference/inference/responses) |

首发网关合同为 OpenAI 模型 → `POST /v1/chat/completions`、DeepSeek 模型 → 同一 Chat 路径、Claude 模型 → `POST /v1/messages`。每条绑定验证过的供应商、模型和凭据。支持文本请求、流式和非流式、一个基础客户端函数工具及其结果回传。服务端搜索、托管工具、文件、音视频、通用透传和任意跨协议翻译由后续单独验收。Anthropic Messages 可测试 `x-api-key` 和受管 Claude Code 的 Bearer 形式，定义允许的版本头与 beta 功能。OpenAI 兼容 SDK Base URL 使用含 `/v1` 的入口，Anthropic SDK 及 Claude Code 按实际拼接规则使用网关根地址。

## 客户端和研发工具

| 客户端 | 自定义 Base URL / API Key | Chat Completions | Responses API | Anthropic Messages | 流式、工具及接入边界 |
| --- | --- | --- | --- | --- | --- |
| OpenAI SDK / Anthropic SDK | 支持各自 SDK 的自定义地址和凭据，使用平台子 Key | OpenAI SDK | OpenAI SDK | Anthropic SDK | 用标准 SDK 验收三条 P0 路由，分别验证流、工具增量、工具回传与结束用量。 [OpenAI Python SDK](https://github.com/openai/openai-python) · [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) |
| Claude Code | 官方文档提供网关地址设置；LiteLLM 指南列出 Bearer 凭据 | 非其原生协议 | 非其原生协议 | 有文档，使用 `/v1/messages` | P0 兼容冒烟。验证多轮、基础本地工具触发、模型名及是否需要计数路径或额外头。 [Claude Code 网关](https://code.claude.com/docs/en/llm-gateway) · [LiteLLM 接入](https://docs.litellm.ai/docs/proxy/client_setup/claude_code) |
| Codex CLI / 桌面 Codex 功能 | 自定义 provider 的 `base_url` 和 `env_key`；桌面用所选版本验证配置加载 | 官方 provider 配置目前只接受 `responses` | 有文档，P1 先验 HTTP/SSE | 非其原生协议 | 验证模型发现、模型元数据、工具增量和多轮结果回传。WebSocket 及桌面行为随版本验证。 [配置参考](https://learn.chatgpt.com/docs/config-file/config-reference) · [LiteLLM Codex 指南](https://docs.litellm.ai/docs/proxy/client_setup/codex_cli) |
| ChatGPT 普通聊天（网页/桌面） | 未确认官方聊天可改为企业自建模型地址及子 Key；普通聊天纳管暂不规划 | 作为网关客户端未确认 | 作为网关客户端未确认 | 作为网关客户端未确认 | ChatGPT 订阅与 API 计费独立。桌面内 Codex 功能单独验证；若未来希望纳管聊天，先核查企业控制台及官方扩展的能力边界。 [OpenAI 计费说明](https://help.openai.com/en/articles/9039756-managing-billing-for-chatgpt-and-the-api-platform) · [LiteLLM 客户端边界](https://docs.litellm.ai/docs/proxy/client_setup/overview) |
| WorkBuddy 桌面 | 官方文档支持自定义 URL、API Key、模型名及完整 URL 方式 | OpenAI 兼容接入可行，实际路径待验证 | 待验证 | 待验证 | 有模型工具能力配置。实际流式、工具闭环、辅助请求和企业客户端策略待 PoC。IDE、插件和 CLI 单独核验。 [WorkBuddy 模型配置](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Model) |
| Qoder IDE | 官方文档支持自定义 Base URL、API Key、Model ID | 有文档 | 有文档 | 有 Anthropic Compatible 选项，实际 Messages 路径待验 | 验证公司套餐、地区、模型校验、多轮 SSE 和工具事件。Repo Wiki 等固定模型功能按产品边界评估。 [Qoder IDE 自定义模型](https://docs.qoder.com/zh/qoder/custom-models) |
| Qoder CLI | 官方文档列 BYOK 向导；官方发布帖列 Base URL、Key 和协议，企业套餐待验证 | OpenAI-compatible，精确路径待验证 | CLI 是否提供该选项待验证 | Anthropic-compatible，精确路径待验证 | 以目标账号目录与 CLI 版本为准，验证流式、工具与辅助请求。 [Qoder CLI 自定义模型](https://docs.qoder.com/cli/custom-models) · [官方发布帖](https://forum.qoder.com/t/qoder-cli-now-supports-custom-models/12444) |

## 验证方法

1. 对 P0 路由用企业授权的测试凭据，先直连上游采集脱敏协议样本，再经 LiteLLM 与平台调用。比对路径、鉴权、模型标识、消息结构、终止语义和用量。用正式发布的模型 ID 生成试点白名单。
2. 每条路由覆盖普通响应、SSE、工具调用及结果回传、错误、断开、缓存命中与未命中。比对网关日志的请求 ID、归属、提供方实际用量与价目版本。SSE 无终止用量时验证待核对和预留处理。
3. 对拟纳管客户端，用受管 Windows 终端和实际企业套餐在测试域名录制经授权的请求路径、鉴权头类型和事件轮廓。检查 Base URL 拼接、自签或企业 CA、代理、模型发现、常用工具、多轮、撤销后行为，以及会走产品云服务的辅助功能。保留脱敏样本，不截图存明文 Key。
4. 对尚无证据的协议，先查目标版本的配置和官方支持，再用最小模型请求及流式工具回合确定路由。成功通过准入、归因、审计和费用核对的组合作为发布清单。地区、订阅和产品版本变化触发回归。
