# LiteLLM 本地模拟 PoC

固定 LiteLLM **1.111.0**，使用本地合成上游。脚本只记录请求协议、成功或失败事件类型及经过允许列表的用量字段名。请在隔离环境使用临时数据库和合成凭据。运行日志保存在项目外的临时目录。

## Docker Compose 复现

从当前目录执行。下列 PowerShell 命令为进程注入随机测试值。Compose 仅将 fixture 和推理代理端口绑定到回环。PostgreSQL 为临时实例。

```powershell
$env:POC_MASTER_KEY = 'sk-' + [guid]::NewGuid().ToString('N')
$env:POC_FAKE_PROVIDER_KEY = 'sk-' + [guid]::NewGuid().ToString('N')
$env:POC_SALT_KEY = 'sk-' + [guid]::NewGuid().ToString('N')
$env:POC_PG_PASSWORD = [guid]::NewGuid().ToString('N')
docker compose -p ai-token-litellm-poc config --quiet
docker compose -p ai-token-litellm-poc up -d
# 等待 wget/curl 或 Invoke-RestMethod 检查就绪
Invoke-RestMethod 'http://127.0.0.1:18400/health/liveliness'
uv run --no-project --python 3.12 probe.py
docker compose -p ai-token-litellm-poc down
```

如果本地配置了 `POC_UPSTREAM_ROOT` 或 `POC_PROXY_ROOT`，运行 Compose 探针前清理该进程的旧值。以上流程包含 PostgreSQL，Virtual Key 与限额用例启用。Redis 多副本协调留待目标环境验证。

## 原生协议验证

Docker 不可用时可在隔离 Python 3.12 环境运行。下列命令中的两个路径变量分别指向项目外的虚拟环境与日志目录。

```powershell
uv venv --python 3.12 $pocVenv
uv pip install --python "$pocVenv/Scripts/python.exe" 'litellm[proxy]==1.111.0'
& "$pocVenv/Scripts/python.exe" run_native.py --logs $pocLogs --protocol-only --startup-timeout 150
```

原生模式需调用 PostgreSQL 能力时，另行准备专用 PostgreSQL 与固定版本的代理数据库依赖，设置私有 `DATABASE_URL` 并移除 `--protocol-only`。Windows 试验时，Prisma Python 客户端生成使用 UTF-8 及独立版本缓存。使用系统 HTTP 代理时，为本地测试进程配置回环地址的 `NO_PROXY`。模拟模型服务包含 Chat、Responses 和 Messages 的 JSON 与 SSE 样本，以及 Chat 函数工具结果回合。回调样本用于验证钩子，生产级签名和持久重试方案见 [安全设计](../../SECURITY.md)。实际执行见 [运行记录](RESULTS.md)。
