# LiteLLM PoC 运行记录

运行日期 2026-11-27。原生运行环境为 Windows、Python 3.12.16、LiteLLM 1.111.0 和 LiteLLM Proxy 1.111.0。使用本地回环模拟上游和即时生成的合成凭据，未配置商业许可。

## 已执行的模拟协议用例

| 用例 | 结果 | 证据 |
| --- | --- | --- |
| OpenAI Chat JSON | 通过 | 输入 11、输出 7、总量 18。 |
| DeepSeek Chat JSON | 通过 | 输入 11、输出 7、总量 18；本用例未覆盖 DeepSeek 缓存字段。 |
| OpenAI Chat SSE | 通过 | 终态 usage 总量 18 和 `[DONE]`。 |
| DeepSeek Chat SSE | 通过 | 终态 usage 总量 18 和 `[DONE]`。 |
| OpenAI Responses JSON | 通过 | 输入 11、输出 7、总量 18。 |
| OpenAI Responses SSE | 通过 | `response.completed` 携带终态 usage。 |
| Anthropic Messages JSON | 通过 | 非缓存输入 11、输出 7、缓存读取 5。 |
| Anthropic Messages SSE | 通过 | `message_start` 和 `message_delta` 用量、`message_stop`。 |
| Chat 函数工具 | 通过 | 收到 `lookup` 工具调用，用对应 ID 回传结果后获得正常响应。 |
| 成功与失败回调 | 通过 | 模拟接收端收到两类带代理调用 ID 的允许列表事件。 |

协议探针命令为 `python run_native.py --logs <临时日志目录> --protocol-only --startup-timeout 150`，退出码 0。它验证代理实际经 HTTP 调用模拟上游。流式验证检查 SSE 帧和 usage，目标环境的流式延迟、流式工具分片及断线行为需另测。回调验证覆盖钩子和事件形状，业务请求 ID 映射、签名、重放与持久补偿需另测。

## PostgreSQL 与限额用例

Windows 原生环境启动了隔离 PostgreSQL 16.15，并由 LiteLLM 完成其自身数据库迁移。首次生成 Prisma 客户端遇到 Windows 编码问题。使用 UTF-8 和独立缓存生成 Prisma Python 0.11.0 客户端后，代理到达就绪状态并处理了一个模拟 Chat 请求，随后提前关闭。另用进程内 ASGI 启动验证，仍出现 Prisma 查询引擎的 HTTP 502 或回环连接失败。未得到下列能力的成功运行证据。

| 数据库用例 | 结果 | 静态证据与复测 |
| --- | --- | --- |
| Virtual Key、模型白名单、禁用、恢复和删除 | 未通过本机环境验证 | 固定版本源码与官方文档列出相应能力。用带 PostgreSQL 的 Compose 探针验证各动作及拒绝后的上游调用行为。 |
| Key RPM | 未通过本机环境验证 | 官方文档列出 RPM。以同一 Key 在同一分钟内连续发起两次调用，验证限速。 |
| Key 预算 | 未通过本机环境验证 | 官方文档列出预算。以有明确模拟价格的模型和低预算触发拒绝，并验证预算消耗与拒绝原因。 |

协议模式主动跳过以上三个用例。数据库模式使用 `run_native.py` 并提供独立 `DATABASE_URL`，同时尝试了 ASGI 本地测试路径。连接失败不能判定功能不受支持，复测以官方镜像中数据库用例的实际输出为准。

## 其他检查和验证边界

- `ruff check docs/poc/litellm` 通过。
- `docker compose -f docs/poc/litellm/compose.yaml -p ai-token-litellm-poc config --quiet` 通过，使用合成变量解析配置。Docker Desktop Linux 引擎在本机未就绪，容器联调未执行。
- OpenAI、DeepSeek 和 Anthropic 的真实供应商调用均未执行。区域网络、企业账号、实际 usage、供应商工具行为、价格及账单仍待验证。Redis 多实例协调、故障降级和真实账务并发尚无实测证据。

## Prisma 连接专项复查

2026-11-27 在 Windows 原生 PoC 上完成。PoC 依赖仍为 Python 3.12.16、LiteLLM 与 Proxy 1.111.0、Prisma Client Python 0.11.0、Proxy Extras 0.4.118.post1、psycopg 3.3.9、HTTPX 0.29.0 和 PostgreSQL 16.15。系统默认 Python 为 3.13.12，实测命令显式使用 PoC 虚拟环境中的解释器。Prisma Client 期望的引擎提交和 Windows Query Engine 二进制均为 `ac9d7041ed77bcc8a8dbd2ab6616b39013829574`，打包 Schema 文件存在。

### 根因与改动

原日志显示 PostgreSQL 打印就绪后，在 Prisma 查询实际到达时收到 fast shutdown，查询被取消，子进程以 `0xC000013A` 退出。该状态表示 Windows 控制台 Ctrl+C 终止。中止后出现客户端 502 或回环连接错误。现有日志无法识别控制事件发送方。直接验证了账号、数据库、Schema 和匹配的引擎版本。同一个存活的引擎在有无显式回环 `NO_PROXY` 两种设置下均返回 200，所以本次不修改代理环境配置。 [Microsoft NTSTATUS](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-erref/596a1078-e883-4972-9bbc-49e60bebca55)

复测让诊断进程以 Windows 无控制台模式启动专用 PostgreSQL，并在全程持有进程句柄。LiteLLM 使用原项目配置，所有检查完成后关闭所持有的测试实例。未更改 LiteLLM、Prisma、应用配置、持久 Schema 或已有数据。原生 DSN 指向 `127.0.0.1:15490/litellm_poc`，测试角色为 `litellm_poc`，使用隔离集群已有的本地 trust 规则。Compose 的 `postgres:5432/litellm_poc` 使用容器服务名及部署注入密码，未发布 PostgreSQL 主机端口。Docker Desktop 引擎未连接。

### 实际命令与结果

`$runtime` 为诊断运行目录 `<本地工作目录>\work\litellm-runtime`。脚本与原始日志保留在该目录，项目配置和业务代码无需启用诊断脚本。

| 实际命令或探针操作 | 结果 |
| --- | --- |
| `git status --short --branch --untracked-files=all`，`Get-FileHash` | 开始前已核对无提交的工作区和现有未跟踪文件。记录了 PoC 代码、配置及 Compose 的 SHA-256。 |
| `python --version`，`venv-db/Scripts/python.exe --version` 和 `importlib.metadata.version()` | 系统 3.13.12，PoC 3.12.16。LiteLLM 和 Prisma 依赖版本如上。 |
| `pg_ctl -D <pgdata> status`，`pg_isready -h 127.0.0.1 -p 15490 -t 2`，另检查本机 5432 | 开始前 PoC 实例未启动，两个端口均无响应。 |
| `query-engine.exe --version`，检查 Prisma Client 的 `expected_engine_version`、Windows 引擎及打包 Schema 文件 | 二进制可执行且提交与 Client 预期相同，Schema 文件存在。 |
| `docker version --format '{{.Server.Version}}'`，`docker compose config --format json` | 前者无法连接 Linux 引擎，后者成功解析配置。连接信息核对时仅输出主机、端口、数据库和密码存在状态。 |
| `venv-db/Scripts/python.exe fix_diagnostic.py` | 首轮沙箱回环连接超时。测试实例按计划关闭，保留该失败日志。 |
| `venv-db/Scripts/python.exe fix_diagnostic_authorized.py` | 回环授权后 `pg_isready` 退出码 0，`psql -X -w -h 127.0.0.1 -p 15490 -U litellm_poc -d litellm_poc -tAc "SELECT 1"` 返回 1。独立 Prisma 和 LiteLLM 使用的端口自选引擎分别查询到 42 与 43，退出码 0。 |
| `venv-db/Scripts/python.exe fix_proxy_ab.py` | 同一存活引擎的 `GET /status` 在两种 `NO_PROXY` 设置下均为 HTTP 200。退出码 0。 |
| `venv-db/Scripts/python.exe fix_validation.py` 中的 PostgreSQL 标识、Schema 和迁移对照 | 数据库和角色均为 `litellm_poc`，端口 15490，Schema 为 `public`。两个核心表均存在。包内和数据库各有 252 条已应用迁移，无缺失、多余或未完成记录。 |
| 同一脚本启动 `litellm.exe --config <config.yaml> --host 127.0.0.1 --port 18404`，请求 `GET /health/readiness` | HTTP 200，`status=healthy`，`db=connected`。 |
| 同一脚本请求两次 `GET /key/list?page=1&size=1` | 写读测试前后均 HTTP 200，返回符合契约的空列表。本次未新建持久 Key。 |
| 同一脚本通过 Prisma 执行 `SELECT 42` 和临时表事务 | 查询返回 42。写入一行并读回 2718，提交自动清理临时表，随后再次确认表不存在。 |
| `pg_ctl -D <pgdata> -m fast -w stop` | 验证完成后正常停止本次启动的实例。完整复测退出码 0。 |

本机 Prisma 连接及五项回归已通过。原始成功日志位于 `fix-validation-8848`。这一轮验证的是 Virtual Key 查询。旧记录中的 Key 生命周期、预算、RPM 和 Docker 容器运行状态仍待对应测试，业务开发未开始。
