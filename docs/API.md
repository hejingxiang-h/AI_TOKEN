# API 契约设计

管理接口由 FastAPI 提供，模型请求使用原协议，回调使用单独的内部契约。本阶段为接口设计。

## 管理接口

| 方法与路径 | 说明 |
| --- | --- |
| `POST /api/v1/auth/login`、`/refresh`、`/logout`；`GET /api/v1/me` | 认证、撤销会话及查询当前授权。 |
| `GET/POST /api/v1/users`、`/departments`、`/projects` | 作用域内读取，创建和写入由全局管理员执行。成员、部门和主管授权走明确的子资源。修改状态及属性使用对应资源的 `PATCH /{id}`。 |
| `POST /api/v1/key-grants` | 管理员建立领取授权，并校验用户、部署范围及模型集合。 |
| `POST /api/v1/key-grants/{id}/claim` | 仅 Key 所有人可发起。创建并返回一次明文，`Cache-Control: no-store`。重试领取不回传旧明文。 |
| `POST /api/v1/key-grants/{id}/rotate`、`/pause`、`/resume`、`/revoke` | 管理员操作、记录原因和审计。轮换沿用同一授权的模型范围和额度。管理员核准旧 Key 截止时间，撤销后关闭后续准入。 |
| `GET /api/v1/keys`、`/usage/summary`、`/requests`、`/requests/{id}` | 可见 Key 掩码、确认金额、待核对计数、明细与授权维度。 |
| `GET/POST /api/v1/model-routes`、`/price-versions`、`/quota-policies` | 模型、价目、额度配置由管理员执行；报表的授权范围在服务端校验。 |
| `GET /api/v1/audit-events`、`/alerts`；`POST /api/v1/alerts/{id}/acknowledge`、`/close` | 管理审计、可见告警与管理员处置。证据访问采用独立权限。 |
| `GET/PATCH /api/v1/settings`、`POST /api/v1/settings/gateway-state` | 管理员读写系统策略和启停。变更校验当前修订版本并写审计。 |

JWT 会话与模型凭据按接口分离。管理 API 使用 Pydantic 2.x 校验。列表统一分页和明确排序，金额使用十进制字符串和 ISO 币种，时间使用 ISO 8601。服务端固定权限范围后再应用客户端筛选。不存在或越过数据范围的详情使用 404，已知用户缺少动作权限使用 403。

## 阶段六实际接口

以下是阶段六 FastAPI 暴露的主要路径，均以 `/api/v1` 开头。后续网关、账务和告警仍使用上文及后文的设计契约。

| 模块 | 已实现接口 |
| --- | --- |
| 会话 | `POST /auth/login`、`/auth/refresh`、`/auth/logout`、`/auth/password`；`GET /me`。Refresh Token 使用 HttpOnly Cookie。 |
| 组织 | 用户、部门、项目的列表、详情、写入和状态变更；部门树、部门成员、主管授权、项目成员；`GET /roles`。 |
| 模型 | `GET/POST /providers`、`PATCH /providers/{id}`；`GET/POST /model-routes`、`GET/PATCH /model-routes/{id}`、`GET/POST /model-routes/{id}/prices`、`POST /model-routes/{id}/probe`。供应商凭据在 LiteLLM 运行环境配置。 |
| 子 Key | `GET /keys`、`GET /keys/{id}`、`POST /keys/grants`、`POST /keys/{id}/claim`、`PATCH /keys/{id}`。状态变更限超级管理员，领取限所有者。Key 业务状态由 FastAPI 推理准入检查。 |
| 配额 | `GET/POST /quotas`、`GET/PUT /quotas/{id}`。金额以 USD 计，租户级规则仅管理员可读。普通用户读取本人或自己的 Key 配额，主管可额外读取授权部门及范围内用户和 Key 的配额。项目共享规则仅管理员可读。 |

## 模型接口

| 方法与路径 | 凭据 | 发布范围 |
| --- | --- | --- |
| `POST /v1/chat/completions` | 平台子 Key Bearer | P0 OpenAI 和 DeepSeek 模型别名。 |
| `POST /v1/messages` | 平台子 Key，使用受控 `x-api-key` 或 Bearer | P0 Anthropic。校验 `anthropic-version` 和允许的功能头。 |
| `POST /v1/responses` | 平台子 Key Bearer | PoC 与 V1.1 候选。默认不对外开放。 |

`X-Request-ID` 由平台生成。业务接口返回稳定的错误码和脱敏原因，模型接口遵循所选协议格式。凭据无效返回 401，权限不匹配返回 403，参数错误返回 400，限流和预算拒绝返回 429，关键依赖失效返回 503。已发送 SSE 响应头后，在协议允许时下发错误事件，无法表达时记录非正常终止。用于限流的 `Retry-After` 按可确定窗口设置。模型请求在派发不确定时不自动重放。

## 内部回调

`POST /internal/v1/litellm/events` 只绑定内部路由。发送端为 LiteLLM 自定义回调适配器。字段白名单包括 `schema_version, source, event_id, request_id, proxy_call_id, upstream_request_id, event_type, model_route_hint, occurred_at, safe_usage, outcome_code`。业务关联使用 FastAPI 生成的 ID，若标签稳定性未通过验证，则按经验证的代理请求标识或待核对证据关联，避免关联到其他请求。回调金额只作线索，正式金额由业务价格快照复算。

1. 认证、校验来源和签名后限制体积与字段类型。按 `(source, event_id)` 在业务库写入 inbox，提交后返回 202。相同 ID 与相同正文摘要返回 200，表示已接收。同 ID 异文返回 409 并告警。
2. 适配器按代理调用标识和终态类型生成稳定事件 ID，重投保持同一事件 ID、同一正文及新的签名时间。签名与时间窗见 [安全设计](SECURITY.md#回调认证与重放防护)。5xx 和暂时性网络失败可退避重试；401、403、409 及不可恢复的 4xx 记录原因并进入人工处理。
3. 消费任务对 inbox 行加租约，按请求 ID 或唯一代理关联 ID 匹配原账务。先到回调、迟到、重复和乱序允许安全重跑。已结算的冲突数据进入复核，未结算的数据须通过来源、完整性和模型版本核对。
4. 异步钩子不可保证宕机时送达。接收端持久化只保护已收到事件。若代理内无法可靠持久化发送，使用平台流响应证据、定期核对待结算调用以及验证过的代理日志 API 补偿。限次重试后保留失败状态，人工核对及追加分录留痕。

## 阶段七当前实现

`GET /v1/models` 按有效子 Key 和平台模型授权列出目录。JSON/SSE 转发覆盖 Chat Completions、Messages，以及显式启用的 Responses 候选。每个目录别名注册一个推理协议。模型路由状态与管理接口的 Key 业务状态独立，`gateway_status` 目前报告 `unavailable` 或 `unknown`，后者表示已配置但尚未报告实时连通性。

`POST /internal/v1/gateway/usage` 仅私网。回调体包含 `event_id`、`request_id`、`proxy_call_id` 和规范 usage。回调头 `X-Hook-Timestamp` 是 Unix 秒，`X-Hook-Signature` 是 HMAC-SHA-256 十六进制签名，签名内容为时间戳、HTTP 方法、该路径和原始正文 SHA-256，各项用换行连接。重复且同内容返回 204，冲突返回 409。下文的完整事件 Inbox 契约仍作为后续对账扩展。
