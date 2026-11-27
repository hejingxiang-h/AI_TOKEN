# 生产部署与运维

交付的是生产部署配置。DeepSeek 已通过本机模型链路验收。生产服务器、正式证书、容器部署及实际网络策略需要在目标环境验证。

## 拓扑和前置条件

- Linux 主机、Docker Engine、Compose v2、Python 3.9+、POSIX shell、OpenSSL 与 GNU coreutils。正式域名指向 Nginx，准备证书链与私钥。Compose 只发布 Nginx 的 80/443。
- Vue 构建进 Nginx 镜像。Nginx 提供静态文件，转发 `/api/v1/` 管理 API 与三个允许的模型路径 `/v1/models`、`/v1/chat/completions`、`/v1/messages`，禁用 SSE 响应和请求缓冲，限速登录。Responses 在此配置关闭。
- FastAPI、LiteLLM、PostgreSQL、Redis 与风险 worker 分服务部署。PostgreSQL 分业务和代理数据库，Redis 开启 AOF，数据使用独立持久卷。LiteLLM 管理接口只在代理私网开放。生产网络应将代理出站限制在批准的供应商地址及所需 DNS 和证书服务。Compose 的出站网络提供路由，具体目的地限制由宿主机或外部网络策略执行。
- `APP_EDGE_PROXY_IP` 是 Compose 内 Nginx 的固定地址，也用于 FastAPI 的可信代理配置。按主机现有网络调整子网与 IP，避免冲突。此配置假定客户端直接连接 Nginx。若上游有额外负载均衡器，先按实际拓扑审查转发头和来源 IP。
- 容器以明确的服务角色持有所需凭据。PostgreSQL、Redis 与业务后台的探活可用于判断启动状态。健康检查不替代 worker 按周期完成及结算积压监控。

## 配置与首次启动

从项目根目录执行。安装模板前确认目标配置文件不存在，保留现有部署配置。

```sh
test ! -e .env.production && cp .env.production.example .env.production
sh deploy/production/deploy.sh check
```

在 `.env.production` 设置正式域名、不可复用的发布标签、机密目录及边缘网络。模板中的域名和发布标签仅用于配置解析。将机密目录放在仓库外，由部署操作者管理，父目录权限 0700。文件仅挂载给需要的容器。使用 Compose 单机文件型 secrets 时需保证容器运行用户可读，挂载只读。若宿主通过 0444 允许非 root 容器读取，务必以父目录及宿主机 ACL 限制读取。部署机应限制 Docker 管理权限。

| 文件名 | 用途 |
| --- | --- |
| `postgres_password`、`app_db_password`、`proxy_db_password` | 分别生成随机密码，供 PostgreSQL 启动及数据库所有者连接。 |
| `redis_password`、`jwt_secret`、`callback_secret` | 分别随机生成，JWT 和回调密钥至少 32 字节。 |
| `proxy_master_key`、`proxy_salt_key` | 独立随机值。Master Key 使用 LiteLLM 支持的 `sk-` 格式，仅代理侧加载。 |
| `deepseek_api_key` | 已授权的 DeepSeek 供应商 Key，仅代理加载。 |
| `proxy_service_key` | 首次启动前准备空的普通文件，由部署脚本签发受限 Virtual Key 后写入。 |
| `tls_certificate.pem`、`tls_private_key.pem` | 正式证书链和私钥，仅 Nginx 加载。 |

将随机值直接送入机密文件或由企业密钥系统下发。除证书外，每个文件只写一行 UTF-8 值，使用 LF 换行。启用回调时，代理和后端共用同一回调密钥。业务后端只持有推理服务 Key。环境文件用于非敏感参数，禁止放入生产凭据。

```sh
sh deploy/production/deploy.sh prepare
sh deploy/production/deploy.sh migrate
sh deploy/production/deploy.sh start-proxy
sh deploy/production/deploy.sh provision-key
sh deploy/production/deploy.sh initialize-admin
sh deploy/production/deploy.sh start
sh deploy/production/deploy.sh status
```

`prepare` 检查域名和版本、构建 FastAPI 及 Vue/Nginx 镜像，仅启动数据服务。`migrate` 分别启动一次性 Alembic 和 LiteLLM Prisma 迁移任务。业务服务不自行迁移，代理运行配置关闭自动更新 Schema。`initialize-admin` 交互输入第一个管理员名和密码，无默认密码。已有管理员的系统跳过该动作。`start` 先核对业务库已到目标迁移版本。启动后通过后台创建供应商、同名 `deepseek-flash` 模型、当前生效 USD 价目和配额，再签发临时平台子 Key。按目标模型上下文上限和准入预留算法审核输入上限、TPM 和测试额度。

服务 Virtual Key 首次签发为独立推理凭据，90 天到期，模型白名单限制为 DeepSeek。轮换时从内部管理面先生成新 Key，替换秘密文件，重新创建后端容器并验证后再撤销旧 Key。单机 Compose 文件重命名后需要重建容器才会挂载新 inode。证书也按相同原则更新并复验域名和证书链。凭据置换后若无法确认状态，先从受控代理管理面核对。

## 部署验收与日常运维

- 检查容器状态、TLS 证书链、HTTP 跳转、Vue 页面和 `/api/v1/me` 的登录会话。普通客户端访问内部回调、LiteLLM Key 管理及 Swagger 路径应返回 404。检查宿主机只监听指定的入口端口，并从业务网段验证数据库、Redis 与代理管理面不可直接访问。
- 用短期、低额度的平台子 Key 从公开 Base URL 演练模型列表、普通 JSON、SSE 和完整工具回合。核对短期用量、账本归属及告警。撤销测试 Key 后再次确认拒绝。发起受控重启后复检服务和持久数据。
- 日志按服务使用 Docker JSON 驱动，每个文件 10 MB，保留 5 个。通过 `docker compose --env-file .env.production -f compose.production.yaml logs --tail=100 backend worker nginx litellm` 查看。禁止在事件单中附带授权头、机密文件或完整输入。部署监控需覆盖代理依赖、worker 告警采集、恢复积压和卷容量。
- 若 HTTPS 或前端失败，先查 Nginx 容器状态、证书可读性、证书与域名匹配、80/443 占用。状态 502/503 时检查 `backend`、`postgres`、`redis` 和 `litellm` 的健康及上次迁移。若流式中断，核对上游用量与账本，不盲目重放计费请求。

## 备份、恢复、升级与回滚

```sh
sh deploy/production/backup.sh /var/backups/ai-token-gateway
sh deploy/production/restore.sh /var/backups/ai-token-gateway/gateway-时间戳 restore_dr01
```

恢复标签使用以 `restore_` 开头的小写字母、数字和下划线，例如 `restore_dr01`。备份脚本生成业务和代理两份 PostgreSQL 自定义归档及 SHA-256 校验，只有完整产物才会移入最终目录。恢复脚本校验两份文件并只创建新的演练数据库，记录恢复日志。任何切换数据源或删除正式库必须走单独变更审批。备份目录应加密、限制访问并做异地保留。Redis 的 AOF 卷和 TLS、凭据属于独立资产，按部署方策略保护。两库导出不在同一事务，用于切换或升级时先停收新请求、等待在途交易和结算队列收敛，再保留两库、Redis 与配置的对应恢复点。

升级前保留当前 Git 版本、镜像标签或摘要、配置版本和最近验证过的备份。先在预发布环境完成迁移和恢复演练，再停流、备份，分别执行两种一次性迁移，更新容器后复测。小版本仍需确认模型协议和当前账本兼容性。回滚应用前核对旧版可读写当前数据库结构。涉及不兼容迁移时，从备份恢复到独立库，核对关键表行数、费用归属和恢复点之后的调用证据，再按审批切换。避免自动降级迁移或复用旧发布标签覆盖镜像。

## 本次本地验证

生产 Compose 表达式和配置解析、端口与隔离断言通过。原生 Nginx 1.28.3 使用合成证书、回环端口与模拟 API 完成语法、HTTPS、Vue、路径隔离、代理头、登录限速及未缓冲 SSE 检查。Shell 脚本通过语法校验。模拟 Compose 执行了备份、恢复到新库名及校验损坏归档后拒绝恢复。阶段十另验证了原生 PostgreSQL 的实际备份和恢复。LiteLLM 1.111.0 的独立迁移命令在隔离 PostgreSQL 空库执行成功，落库 252 条 Prisma 迁移。本机 Docker Linux 引擎未就绪，生产容器、运行时网络、正式证书和主机故障恢复未联调。
