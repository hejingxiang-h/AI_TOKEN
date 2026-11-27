# 阶段七架构决策：FastAPI 统一鉴权代理

- 状态：已确认，实施与集成验收待启动。
- 日期：2026-11-27。
- 依据：[子 Key 同步架构检查](KEY_SYNC_ANALYSIS.md)、[系统架构](../../ARCHITECTURE.md)、[模型接入](../../MODEL_INTEGRATION.md)。

## 最终架构与当前差距

客户端使用 `tg_` 子 Key，经 Nginx 进入 FastAPI Gateway，再由 FastAPI 使用私网 LiteLLM 服务 Virtual Key 转发至 LiteLLM Proxy 和模型供应商。LiteLLM 1.111.0 的自定义 Virtual Key 创建要求 `sk-` 格式。平台子 Key 仍按现有方式签发、仅展示一次并保存摘要与掩码，首版无需逐 Key 注册到 LiteLLM。

现有 FastAPI 注册了健康、鉴权、组织、模型目录和 Key/配额管理路由。Nginx 的推理入口已经指向 FastAPI，且关闭流式缓冲。FastAPI 推理准入和转发尚待实现。现有 Key 领取及查询 Schema 的 `not_synced` 是固定值。实施时保留现在的 Key 数据模型和字段，以业务 `state` 表示待领、启用、暂停、撤销或过期，以独立的按路由服务状态表示 `ready`、`unavailable` 或 `unknown`，原 API 的 `gateway_status` 先制定兼容过渡。路由就绪不代表该 Key 获准调用。需要增列或新表时先提交 Alembic 迁移方案，说明默认值、旧数据回填、兼容读取和回退。既有摘要的 HMAC 演进需要单独制定迁移与重发方案。

## 请求、凭证与配额

1. FastAPI 从经协议允许的凭据头提取 `tg_`，拒绝冲突认证头。以摘要定位现有 Key，检查有效期、Key 和用户状态、用户所属部门、项目启停与有效成员关系，然后校验精确的模型别名白名单、供应商启停和允许协议。认证与归属以数据库为准。
2. FastAPI 生成 `request_id`，记录 `user_id`、`department_id`、`project_id` 和 `api_key_id` 的可信快照。当前 `api_key` 以 `grant_id` 为主键，因此使用该稳定标识；新增独立 ID 时走迁移评审。
3. FastAPI 在转发前执行企业、部门、项目、用户和 Key 五级适用规则。Redis 原子检查 RPM、TPM 和并发租约，记录短期请求状态及辅助预留状态。PostgreSQL 以 Decimal 和价格快照锁定所有适用日、月周期，原子预留金额。Redis 故障时拒绝依赖它的新请求，持久预算以 PostgreSQL 为准。平台拥有最终的权限和金额裁决，LiteLLM 自带限额作为代理侧保护。
4. 丢弃客户端认证、身份和代理控制头，从白名单重建请求。FastAPI 使用独立 LiteLLM 服务 Virtual Key，限制模型及推理路由，从服务端密钥系统注入。服务 Key、LiteLLM Master Key、运维管理凭据和供应商 API Key 分开。仅内部管理服务可调用 LiteLLM 管理接口，FastAPI 推理进程只需推理凭据，Vue 和普通用户无法读取。LiteLLM 负责模型路由、供应商认证、协议适配、上游 usage 与代理日志。

## 业务 metadata 与证据

FastAPI 保存完整的四项可信业务 ID。首版向代理最小传递 `request_id`，优先使用 FastAPI 重建的 `x-litellm-call-id`，同时分别记录代理返回的调用 ID 和供应商请求 ID。客户端提供的同名头、`user`、`user_id`、部门、项目、Key ID、`metadata` 或 `litellm_metadata` 中的保留字段均不能作为业务身份。若确有跨系统诊断需求，经隐私评审和协议实测后，才通过专用 metadata 白名单追加必要的不透明标识。默认禁止转给供应商，禁止记录原始 Key、Prompt 和响应内容。

本机 LiteLLM 1.111.0 `common_request_processing.py` 会解析 `x-litellm-call-id` 并生成响应关联头。 `litellm_pre_call_utils.py` 在 Messages、Responses 等路由预置 `litellm_metadata`，也包含解析 `x-litellm-spend-logs-metadata` 的路径；部分供应商适配路径会挑选转发 `x-` 请求头，因此该头及任意自定义字段的代理持久化、回调保留、上游隔离均待运行验证。平台以自己的请求及归属快照作为账务准则。

## usage、流式和结算

非流式读取最终 usage。SSE 按事件边界解析，保持原协议顺序、背压和状态，Chat Completions 在已验证支持的路由上请求最终 usage，Messages 合并开始和增量的累计字段，Responses 在候选路由读取终态 usage。分协议区分输入、输出、缓存读取和缓存写入，禁止累计字段重复相加。保存安全计量与价目版本，按 `request_id` 幂等结算，释放预留、写账本、调用记录和审计。用户断开、上游超时或终态 usage 缺失且派发结果不确定时进入待核对，不能填零或自动重放。已证明未发出才释放金额预留。经认证的回调用于补证，保持与响应、代理日志和供应商账单交叉核对。

## 实施前验收项

- GPT/DeepSeek Chat 与 Claude Messages 逐路由测试 JSON、SSE、身份字段伪造、客户端取消、usage 缺失、拒绝无上游流量。Responses 暂列候选。
- 用合成 ID 检查 `x-litellm-call-id` 在代理响应、日志和成功/失败回调中的一致性，检测 SDK 协议字段是否污染平台归属。抓取模拟上游请求，确认凭据及业务 metadata 不泄露。
- 验证 Redis 多实例限流与租约、PostgreSQL 并发预留和重复结算、月界与连接故障。用低权限服务凭据验证模型限制及管理接口拒绝。沿用已验证 PoC 基线，在隔离环境新增用例。
