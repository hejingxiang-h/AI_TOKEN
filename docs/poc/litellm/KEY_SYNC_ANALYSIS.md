# LiteLLM 1.111.0 子 Key 同步架构检查

## 结论与证据范围

根因在业务实现。领取只提交本地凭据、状态和审计。两个响应 Schema 都把 `gateway_status` 固定为 `not_synced`，没有持久同步状态、远端资源关系或同步任务。暂停、恢复和撤销也只改变本地状态。当前 Nginx 的模型路由转给 FastAPI，而 FastAPI 尚无推理准入与转发实现。因此，即使运维手工在代理创建了 Key，平台入口仍不能凭该 Key 完成调用。

本机 PoC 虚拟环境通过 `importlib.metadata.version("litellm")` 确认 LiteLLM 1.111.0，解释器为 Python 3.12.16。同时直接调用该安装包的 `from litellm.proxy.proxy_server import app; app.openapi()`，核对了七条路由及请求 Schema。下文以本机 OpenAPI 和安装包源码为准。历史 PoC 已实测 `GET /key/list?page=1&size=1` HTTP 200。本次只读检查，未发起生产或 PoC 写入，创建、限额和跨实例生效仍需隔离联调。

## 当前实现

| 部位 | 实际行为 |
| --- | --- |
| Router | [access.py](../../../backend/app/api/access.py) 的管理员授权是 `POST /api/v1/keys/grants`，所有者领取是 `POST /api/v1/keys/{id}/claim`，返回 `Cache-Control: no-store`。管理员通过 `PATCH /api/v1/keys/{id}` 修改状态。 |
| 生成及事务 | [AccessService](../../../backend/app/services/access.py) 校验状态、有效期、用户和项目成员关系及启用模型，使用事务锁和行锁防止重复领取。由 `secrets.token_urlsafe(32)` 取得 256 位随机输入，拼接 `tg_`。UTF-8 全串做无盐 SHA-256 十六进制摘要，前 12 字符作为展示提示。原文存在于当前请求内存，事务提交后仅在领取响应中发送。重复领取返回 409，响应丢失无法取回。 |
| 数据与状态 | [模型](../../../backend/app/models/access.py) 中 `key_grant` 保存所有者、部门、项目、标签、状态、有效期和创建时间；`key_model` 关联模型 ID；`api_key` 保存 `grant_id`、唯一 `digest`、`hint` 和可空 `last_used_at`。每个 grant 当前只有一条 `api_key`，无远端标识、版本、同步状态或错误字段。过期由读取和转换时按时间判断。数据库设计另规划查找 ID、带版本的 HMAC 和凭据轮换，当前尚未实现。 |
| 生命周期 | `pending → active → paused → active`，待领取或已签发可撤销，撤销终态。恢复复核归属及模型。操作提交本地审计，没有 LiteLLM 请求或缓存失效协作。 |
| 客户端 | [LiteLLM 客户端](../../../backend/app/integrations/litellm.py) 使用环境注入的私网 URL 和 Bearer 管理凭据，HTTPX 超时 8 秒，禁用环境代理，当前被模型健康检查调用。通用错误把 HTTP 状态错误、连接异常、超时或响应格式异常归并为 502，无法区分未知提交、永久失败和待重试。 |
| 前端 | [管理视图](../../../frontend/src/views/ManagementView.vue) 确认后调用领取接口，原文放在组件内存并在弹窗关闭时清空，不写入浏览器存储。显示未同步说明，无同步进度或补偿流程。 |

## 安装版 API 与约束

路由证据在安装包 `litellm/proxy/management_endpoints/key_management_endpoints.py`，参数定义见 `litellm/types/proxy/management_endpoints/key_requests.py` 和同目录 `request_base.py`。下列行号以本地 1.111.0 安装包为准。

| 用途 | 路径及参数 | 源码确认 |
| --- | --- | --- |
| 创建 | `POST /key/generate`，JSON 可传 `key`、`key_alias`、`models`、`duration`、`metadata`、`key_type`、`max_budget`、`budget_duration`、`budget_limits`、`budget_id`、`rpm_limit`、`tpm_limit`。可选 LiteLLM 侧归属 `user_id`、`team_id`、`project_id`。 | 路由 2438 行，依赖 Prisma。未指定 `key` 由代理生成。成功响应 `key` 为原文，`token_id` 为远端摘要，`token` 被重映射为摘要。 |
| 外部生成 | 同一创建接口传 JSON `key`。 | 606、1843–1859 行。必须以 `sk-` 开头，默认最小长度 16，可由 `MINIMUM_CUSTOM_KEY_LENGTH` 调整。开启 `general_settings.disable_custom_api_keys` 返回 403。为同时满足 block/unblock 校验，建议使用符合 `^sk-[A-Za-z0-9_-]+$`、不超过 100 字符的内部 Key。现有 `tg_` 或裸 SHA-256 都会被创建校验拒绝。 |
| 单条查询 | `GET /key/info?key=<远端SHA-256>`。 | 5170 行。也接收原文且会回显查询值，应用应始终用远端摘要。可查询归档，返回派生状态，需要区分 blocked 映射的 `revoked` 和归档的 `deleted`。 |
| 列表与核对 | `GET /key/list?page=1&size=10&key_hash=…&key_alias=…&return_full_object=true`。 | 7401 行。用精确 alias，默认 `substring_matching=false`。按需使用 `status=deleted` 检查归档，默认只查 live。已有运行证据仅为默认分页查询。 |
| 暂停与恢复 | `POST /key/block` 和 `POST /key/unblock`，JSON `{"key":"<远端SHA-256>"}`。 | 8194、8308 行。也支持合法 `sk-` 原文。按目标设置 `blocked=true/false`，未找到可返回 404。代理鉴权读取 blocked 状态，有缓存路径，传播时延需实测。 |
| 撤销 | `POST /key/delete`，JSON `{"keys":["<远端SHA-256>"]}`，也接受 `key_aliases`。 | 4893 行。优先用摘要精确删除，存在删除归档逻辑。重复删除需核对目标已缺失或归档，不能把任意上游 404 当作成功。 |
| 更新策略 | `POST /key/update`，以 `key` 定位，再传 `models`、预算或速率字段。 | 4153 行。模型字段建议使用代理配置中的具体模型别名。鉴权源码 `auth/auth_checks.py` 5046 附近表明空模型列表或通配符可产生宽权限，平台须拒绝空白名单和通配。不能把业务数据库 UUID 直接传成代理模型名，也不能假定 FastAPI 创建模型目录记录会注册代理路由。 |
| Budget 与速率 | 常规 Key 预算使用 `max_budget` 和可选 `budget_duration`，可关联 `budget_id`。OpenAPI 中 `budget_limits` 的每项使用 `budget_duration`、`max_budget` 和可选 `reset_at`。请求和 Token 分钟限额分别用 `rpm_limit`、`tpm_limit`，创建 Schema 为可空非负整数。 | LiteLLM 用浮点预算和自己的计费、周期及缓存。窗口配置、可组合性、预算拒绝、限流与副本共享待联调。LiteLLM 限制只能作为代理侧保护，平台仍负责五级配额和现有 USD Decimal 账务。当前业务已有 RPM 字段，还没有业务级 TPM 规则。 |
| 鉴权 | `Authorization: Bearer <管理凭据>`，Master Key 可以作为 proxy admin。 | `auth/user_api_key_auth.py` 3031 附近用常量时间比较 Master Key。上述路由不在 `_types.py` 637 行的 Master-only 列表。block/unblock 允许 proxy admin，或在目标归属匹配时允许 team/org admin；其他路由也有各自的角色和路径校验。不能把现有健康凭据或任何 management 类型 Key 自动视为有全部写权限，需用预定最小权限账号逐端点证明。 |

`key_alias` 在生成路径先查询重复，Prisma Schema 中 `token` 是主键而 `key_alias` 未声明唯一，不能用 alias 的查后写作为并发唯一保障。`proxy/utils.py` 6956 附近按远端 token 摘要执行 upsert，已存在时更新为空。所查路径未见以 `Idempotency-Key` 实现整个创建请求幂等的保证，不能认为 upsert 会约束前置校验、预算和回调副作用。版本源码优先于滚动文档。 [Virtual Keys](https://docs.litellm.ai/docs/proxy/virtual_keys) · [Budget 和限流](https://docs.litellm.ai/docs/proxy/users)

## 推荐架构与状态

沿用 [已确认架构](../../ARCHITECTURE.md) 的两级认证。客户端继续持有平台 `tg_` Key，进入 FastAPI 准入层。FastAPI 校验带版本的 HMAC 摘要、有效期、归属、精确模型白名单及本地配额。通过后由 FastAPI 丢弃用户认证头，凭独立、最小模型范围的 LiteLLM 服务 Key 转发。LiteLLM 留在私网，负责供应商认证和代理。服务凭据按模型权限集合或业务隔离边界预置并存于密钥系统，管理 worker 与推理进程分别持有管理和推理权限。平台流水应自行归因，不用共享 LiteLLM 服务 Key 的账单替代。

在此方案下，一个平台 Key 不要求存在同名远端记录。平台凭据状态使用 `pending/active/paused/revoked/expired`。另记录网关就绪状态及原因，例如 `not_applicable` 表示无逐 Key 镜像，`gateway_unready` 表示路由或服务凭据未就绪，`ready` 表示准入和转发条件均可用。旧页面的 `not_synced` 需改成明确的就绪状态。现有已签发 Key 无法离线从 SHA-256 转为 HMAC，应通过受控重发，或确认有限期兼容后迁移。存哈希和掩码可以满足平台认证与远端管理定位，二者均不能恢复可用的 Bearer 原文。

若业务明确要求每个 grant 对应一个 LiteLLM Virtual Key，经评审可采用独立的远端 `sk-` 映射，仍让客户端经过 FastAPI。远端凭据原文用于代理认证，需由获准的密钥系统提供；业务库和 Outbox 保存引用、远端 SHA-256、稳定别名和版本。不能把平台 HMAC 当作远端摘要。将同一 `sk-` 原文同时交给用户和代理会扩大凭据可使用范围，现有 `tg_` 又不兼容，需另行确认架构变更。

逐 Key 映射的本地期望状态与远端观测状态分列。建议保存 `desired_state`、`generation`、`sync_status`（`pending/applying/in_sync/retryable_failed/blocked/terminal_failed`）、`observed_remote_state`、`applied_generation`、`last_checked_at` 和脱敏错误码。仅当前代实际生效、组织与模型仍有效时允许新请求。已撤销或已过期始终先在 FastAPI 拒绝。

## 幂等及失败补偿

1. 逐 Key 映射时，先持久化资源意图、稳定 alias 和操作号，与审计、Outbox 同事务。按 `(grant_id, generation, action)` 去重。为同一代准备一次秘密并复用确定的 vault 引用。密钥系统创建应使用创建时唯一约束或条件写，禁止每次重试换原文。先确认可读引用并写入远端摘要，再允许发出代理请求。密钥系统的孤立引用按代次核对后回收。
2. 创建连接超时、读超时、429、5xx 或成功响应解析失败时，按已记录的远端摘要查 `/key/info`，再按稳定 alias 辅助检查。验证环境、归属标记、摘要、模型、限额与有效期。匹配则补记已应用；未命中须考虑读延迟，再以相同摘要对应的同一秘密退避重试。出现 alias 冲突且摘要不符、策略不符或多条记录时暂停并告警，禁止认领他人记录。
3. 远端成功、本地提交失败时，依靠已提交的意图与 Outbox 重启对账，匹配后用版本条件更新本地状态。若授权期间已经撤销，则保留远端删除任务，按已验证归属的摘要处理。平台原文响应丢失时继续遵守一次性展示，用撤销与重签发恢复，不通过重试再次显示旧原文。
4. 暂停及撤销优先提交本地拒绝和 Outbox，远端 block/delete 后核对并落审计。恢复先校验权限、过期、模型及配额，再执行 unblock，确认当前代远端已允许后才放开本地。撤销盖过排队的恢复，任务抢占使用租约和版本比较；旧任务不得回写新版本。在外部 API 无版本栏的情况下串行管理同一映射，发现迟到远端写入则持续纠偏，本地保持拒绝。在途流与新请求分别定义停止规则。
5. 连接错误与权限/参数失败分类、限次退避并告警，按状态和下一次重试时间索引。定期用期望代次重扫长期未完成及漂移记录，验证归属后再执行破坏性补偿。监控冲突、积压、最长未同步时长和撤销传播延迟。

## 后续文件范围与安全验收

| 范围 | 确认后的修改点 |
| --- | --- |
| 业务层 | `backend/app/services/access.py`、`repositories/access.py`、`models/access.py`、`schemas/access.py`、`api/access.py`。新增推理准入、代理转发和摘要版本支持。逐 Key 映射获批时再加映射、Outbox、worker、Alembic 及迁移策略。 |
| 代理层 | `backend/app/integrations/litellm.py`、`core/config.py`，实现独立凭据、结构化错误分类与只读对账。后续如涉及配置，单独评审，保持 Nginx 管理端点隔离。 |
| 界面和测试 | `frontend/src/views/ManagementView.vue`、`src/api/management.ts` 反馈本地状态和网关就绪。扩充 `backend/tests/` 与独立 PoC 用例。 |

管理凭据与推理凭据隔离；只从私网调用管理端点，禁用真实 Key 的请求体、授权头、响应和追踪日志采样。摘要、alias 和关联 metadata 也应限制暴露，metadata 只用不含个人信息的内部关联 ID。LiteLLM 账号、部门或项目 ID 仅在映射已建且授权通过时传递。验证 Key 缓存更新、代理实例重启及副本间同步，尤其是撤销后已有缓存的节点。部署空模型列表、模型配置漂移或凭据缺失时应拒绝发布网关就绪。

## 测试方案

本次执行版本检查、OpenAPI 导出、安装包源码与项目链路比对。以下为待执行的验收，用隔离 PostgreSQL、Redis、LiteLLM 1.111.0 和模拟上游。真实供应商接入再独立验证。

- API 契约：使用本机版本 OpenAPI 和隔离 HTTP 探针对照创建自动/外部 Key、`tg_` 拒绝、禁用自定义 Key、摘要查询、按 alias 列表、block、unblock、delete 和归档。分别以 Master、目标受限管理员、错误归属管理员与普通推理 Key 调用，记录实际状态码。
- 推理和策略：两条模型路由验证白名单、过期、陌生 Key、暂停、恢复、撤销。检查被拒时录制上游请求次数为零。用可控用量实测 RPM、TPM、预算、重置和多实例缓存，业务预算与代理保护分别测量。
- 故障和幂等：并发领取、超时前后两侧写入、远端成功本地提交失败、重复和乱序任务、冲突 alias、远端被误删、撤销与恢复竞争、worker 崩溃与重启。预期无重复业务绑定、无丢失撤销、无重复明文展示。
- 安全和界面：扫描数据库、Outbox、日志、浏览器存储和遥测，验证没有原文。检查刷新、关闭弹窗和再次领取的行为。经过公网入口探测管理 API 隔离，并证明 FastAPI 拒绝的请求不会被代理绕过。

待确认的决策是沿用已批准的 FastAPI 准入与私网服务 Key 模式，还是明确引入逐 Key 远端映射。两种模式采用不同验收条件，建议先验证平台 Key 通过 FastAPI 后能够调用允许的模型。
