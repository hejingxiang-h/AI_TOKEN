# DeepSeek 单供应商全链路补测

2026-11-27，本次只验收 DeepSeek。客户端通过原生 TCP 连接 FastAPI 的统一 `/v1` Base URL。平台以临时 `tg_` Key 鉴权，通过真正从 LiteLLM 1.111.0 创建的推理 Virtual Key 转发到 DeepSeek，业务账本使用隔离 PostgreSQL，限流使用 Garnet。模型为 `deepseek-flash`。代理 Master Key 仅用于创建、验证及撤销服务 Virtual Key。所有运行凭据仅用于隔离测试。

| 检查 | 实际结果 |
| --- | --- |
| 服务 Virtual Key | 创建返回 HTTP 200，限单模型和推理用途。用该 Key 访问 `/key/list` 返回 403。 |
| 平台子 Key | 无 Key 请求 `/v1/models` 返回 401，授权 Key 返回 200 并列出 DeepSeek 路由。测试结束后撤销，再请求返回 401。 |
| 普通 | HTTP 200。34 输入、8 输出 Token。账本已结算 USD 0.0000198。 |
| SSE | HTTP 200，收到 `[DONE]`。34 输入、19 输出 Token。账本已结算 USD 0.000033。 |
| 工具回合 | 模型返回预期函数调用，客户端提交合成工具结果后模型正常继续。两次均 HTTP 200，分别结算 USD 0.000162 和 USD 0.000108468。 |
| 账本 | 四笔请求均保留用户、部门、项目、Key、用量来源和价格版本，共结算 USD 0.000323268。 |
| 清理 | 服务 Virtual Key 删除 HTTP 200，平台子 Key 已撤销，隔离代理数据库副本已移除。 |

首轮普通调用成功后，本机的 Prisma 连接失败，SSE 请求返回 503。进一步运行观察到了 Windows 控制台中断。使用隔离进程组重新运行后通过以上验收。该次复测关闭了代理日志写入来隔离故障，平台账本保持启用并实际结算。生产 LiteLLM 自身的账务日志仍须独立验证。

成功轮四笔请求共 751 输入、113 输出。含首次成功的诊断请求，按官方高峰未缓存费率保守估算合计 0.002562 元，实际费用以供应商账单为准。 [DeepSeek 官方价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

本机 Docker Linux 引擎仍不可用。此次统一 Base URL 直接由 FastAPI 提供，生产 Nginx、容器部署与持续运行验收待完成。其他供应商按后续计划接入。
