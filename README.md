# AI Token Gateway

AI Token Gateway 是面向企业内部的模型调用治理平台。本仓库目前提供基础工程、管理后台的系统健康页和隔离的部署配置。业务鉴权、Key 发放、模型调用和费用结算将在独立验收后实现。

- [项目规范](AGENTS.md)
- [架构](docs/ARCHITECTURE.md)与[数据库设计](docs/DATABASE.md)
- [开发与验收计划](docs/DEVELOPMENT_PLAN.md)
- [阶段进度与实测记录](docs/PROGRESS.md)
- [独立 LiteLLM PoC](docs/poc/litellm/README.md)

## 工程目录

| 目录 | 用途 |
| --- | --- |
| `backend/` | Python 3.12、uv、FastAPI、SQLAlchemy、异步 PostgreSQL 和 Redis、Alembic、Pytest。 |
| `frontend/` | Vue 3、TypeScript、Vite、Element Plus、Vue Router、Pinia、Axios、ECharts。 |
| `deploy/` | 新工程的 PostgreSQL 角色和数据库初始化、Redis ACL、LiteLLM、Nginx 配置。 |
| `docs/poc/litellm/` | 单独运行的技术 PoC，使用独立的 Compose、端口和测试数据库。 |

## 本地开发

准备 Python 3.12、uv、Node.js 22.12 及以上的 22.x 或 24.x 及以上版本、可用的 PostgreSQL 和 Redis。为本工程单独创建业务数据库和登录角色。FastAPI 支持从仓库根目录的 `.env` 或进程环境读取配置。后端使用 `APP_DB_HOST`、`APP_DB_PORT`、`APP_DB_NAME`、`APP_DB_USER`、`APP_DB_PASSWORD` 和 `APP_REDIS_HOST`、`APP_REDIS_PORT`、`REDIS_PASSWORD`。服务端连接不使用前端环境变量存放密码。

在两个终端分别启动。示例默认后端端口 8000，前端端口 5173。

```powershell
Set-Location backend
uv sync --locked
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

```powershell
Set-Location frontend
npm ci
npm run dev
```

前端通过 Vite 代理调用同源的健康接口。后端端口变化时，启动前端前设置 `BACKEND_TARGET`。管理后台根路径跳转到 `/system/health`，Swagger 位于后端的 `/docs`，可通过 `APP_DOCS_ENABLED=false` 关闭。

| 路径 | 行为 |
| --- | --- |
| `GET /health/live` | 仅反映 FastAPI 是否运行。 |
| `GET /health/ready` | 分别运行 PostgreSQL `SELECT 1` 与 Redis `PING`。依赖失败时返回 HTTP 503 及各自状态。 |
| `GET /health` | 就绪检查的别名。 |

常用检查在对应目录执行。

```powershell
# backend/
uv run ruff check .
uv run pytest

# frontend/
npm run lint
npm run format:check
npm run build
```

## Docker Compose

在根目录以 [示例环境文件](.env.example) 为模板配置 `.env`，替换所有 `REPLACE` 值。确保 `LITELLM_DATABASE_URL` 的用户、密码和库名与 PostgreSQL 初始化变量匹配，URL 密码中的保留字符须百分号编码。首次启动新卷时，PostgreSQL 创建互相隔离的业务库和代理库及其角色。已有卷的凭据变更应按数据库运维流程处理。

```powershell
docker compose --env-file .env.example config --quiet
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

默认仅 Nginx 将 8080 端口绑定到宿主机回环地址。PostgreSQL 使用命名卷，Redis 通过环境变量认证，LiteLLM Proxy 的管理端口仅在内部网络可达。Nginx 区分管理 API 和模型路径，并为已规划的模型路径保留 SSE 转发参数。模型路径只会进入 FastAPI，此阶段尚无推理处理器。LiteLLM 模型目录为空，代理密钥和上游供应商密钥由将来的获批部署注入。

阶段四的 Docker 验收是 Compose 配置校验。以上启动命令供目标环境部署验证。本机使用 PostgreSQL 16.15 和 Garnet 兼容服务验证健康检查。正式 Redis 7.4 镜像运行待验证。实际执行结果见 [开发进度](docs/PROGRESS.md)。
