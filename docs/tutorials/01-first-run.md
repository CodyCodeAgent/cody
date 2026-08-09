# 01 · 跑通第一个任务

<div class="tutorial-outcome"><strong>完成后：</strong>你会从 Python 进程调用 Cody，获得包含 output、session_id、run_id 和 usage 的结构化结果。</div>

## 前置条件

- Python 3.10–3.13
- 一个 OpenAI-compatible Chat Completions 端点
- 一个只用于测试的工作目录

## 1. 安装最小 SDK

```bash
python -m venv .venv
source .venv/bin/activate
pip install cody-ai
```

如果还需要命令行、TUI 或 Web，请分别安装 `cody-ai[cli]`、`cody-ai[tui]`、`cody-ai[web]`，或一次安装 `cody-ai[all]`。

## 2. 配置模型端点

```bash
export CODY_MODEL='your-model-id'
export CODY_MODEL_BASE_URL='https://your-provider.example/v1'
export CODY_MODEL_API_KEY='your-api-key'
```

模型 ID 与 Base URL 由服务商决定。Cody 不把 API Key 写入项目配置；生产环境请使用 secret manager 注入。

## 3. 创建一个可验证任务

```bash
mkdir -p /tmp/cody-tutorial
```

创建 `first_run.py`：

```python
import asyncio

from cody import AsyncCodyClient


async def main() -> None:
    async with AsyncCodyClient(workdir="/tmp/cody-tutorial") as client:
        result = await client.run(
            "创建 hello.py，使它输出 'hello from cody'，然后运行并验证输出"
        )

        print("run:", result.run_id)
        print("session:", result.session_id)
        print("tokens:", result.usage.total_tokens)
        print(result.output)


asyncio.run(main())
```

```bash
python first_run.py
test -f /tmp/cody-tutorial/hello.py
python /tmp/cody-tutorial/hello.py
```

## 4. 理解结果

| 字段 | 含义 |
|---|---|
| `output` | Agent 的最终文本结论 |
| `session_id` | 后续多轮对话复用的会话标识 |
| `run_id` | Runtime timeline、artifact 与审计使用的运行标识 |
| `usage` | 输入、输出和总 token 数 |
| `thinking` | 仅在端点和配置支持时存在 |

!!! warning "不要只相信最终文本"
    编码任务的真实完成标准是文件、测试和质量门禁。后续教程会把这些验证保存为 Artifact，而不是只读取一句“已完成”。

## 下一步

继续学习[会话与流式输出](02-sessions-streaming.md)，实时显示文本、工具调用和运行终态。
