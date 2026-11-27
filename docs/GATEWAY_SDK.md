# 开发者调用模型网关

管理员先分配项目、模型白名单及预算，开发者登录后领取平台子 Key。客户端仅使用平台发放的 `tg_` Key。统一 Base URL 为部署入口加 `/v1`；Anthropic SDK 的 base_url 使用部署入口，SDK 自行添加 `/v1/messages`。

运维准备独立 LiteLLM 推理 Virtual Key，仅通过后端环境变量 `APP_LITELLM_SERVICE_KEY` 注入。对应模型别名必须同时存在于 LiteLLM 配置和平台模型目录，平台还需有效的 USD 价格版本与 `APP_GATEWAY_INPUT_BOUNDS` 的已核实模型输入上限。生产路由须确保上游确实限制该输入上限。Responses 默认关闭，受控环境可通过 `APP_GATEWAY_RESPONSES_ENABLED=true` 单独验证。建议先用短有效期、单模型、低风险配额的测试授权。

## OpenAI Python SDK

应用进程设置 `GATEWAY_BASE_URL` 指向部署入口，`GATEWAY_API_KEY` 为已领取子 Key，`GATEWAY_MODEL` 为获准的 Chat 模型别名。示例关闭 SDK 自动重试，避免超时时盲目重发计费请求。

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url=os.environ["GATEWAY_BASE_URL"].rstrip("/") + "/v1",
    api_key=os.environ["GATEWAY_API_KEY"],
    max_retries=0,
)
model = os.environ["GATEWAY_MODEL"]
print([entry.id for entry in client.models.list().data])
messages = [{"role": "user", "content": "用一句话说明质数。"}]
result = client.chat.completions.create(model=model, messages=messages, max_tokens=64)
print(result.choices[0].message.content)
with client.chat.completions.create(
    model=model, messages=messages, max_tokens=64, stream=True,
    stream_options={"include_usage": True},
) as stream:
    for event in stream:
        if event.choices:
            print(event.choices[0].delta.content or "", end="")
        if event.usage:
            print(event.usage)
```

对于单独配置的 Responses 目录别名，调用 `client.responses.create(model=alias, input="你好", max_output_tokens=64, store=False)`。工具限客户端执行的 function 类型。Chat 工具收到 `tool_calls` 后，由应用进行参数校验并按 `tool_call_id` 发送工具结果，应用负责权限和副作用控制。

## Anthropic Python SDK

```python
import os
from anthropic import Anthropic

client = Anthropic(
    base_url=os.environ["GATEWAY_BASE_URL"].rstrip("/"),
    api_key=os.environ["GATEWAY_API_KEY"],
    max_retries=0,
)
reply = client.messages.create(
    model=os.environ["GATEWAY_CLAUDE_MODEL"], max_tokens=64,
    messages=[{"role": "user", "content": "用一句话说明质数。"}],
)
print(reply.content)
```

遇到 401 检查子 Key 与组织状态，403 检查模型授权，429 检查预算和速率。报告故障时提供平台响应头 `X-Request-ID`，无需附带凭据或提示词。以 [网关验收报告](GATEWAY_TEST_REPORT.md) 的覆盖范围为准。
