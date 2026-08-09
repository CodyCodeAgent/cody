# 14 · 多模态与人工交互

<div class="tutorial-outcome"><strong>完成后：</strong>你会发送界面截图，并在 Agent 需要选择或高风险确认时从流中提交响应。</div>

## 1. 构造图片 Prompt

```python
import asyncio
import base64

from cody import AsyncCodyClient
from cody.core.prompt import ImageData, MultimodalPrompt


async def main() -> None:
    image_b64 = base64.b64encode(open("screenshot.png", "rb").read()).decode()
    prompt = MultimodalPrompt(
        text="检查截图中的响应式布局问题，并修复当前项目",
        images=[
            ImageData(
                data=image_b64,
                media_type="image/png",
                filename="screenshot.png",
            )
        ],
    )

    async with AsyncCodyClient(workdir="/tmp/cody-tutorial") as client:
        result = await client.run(prompt)
        print(result.output)


asyncio.run(main())
```

Cody 能承载图片 payload，不代表所选模型端点一定有视觉能力。先确认端点支持对应 MIME 类型和图像输入。

## 2. 打开异步人工交互

```python
from cody.sdk import Cody

client = (
    Cody()
    .workdir("/tmp/cody-tutorial")
    .interaction(enabled=True, timeout=60)
    .build()
)
```

## 3. 在流中响应

```python
from cody.core.errors import InteractionTimeoutError

try:
    async for chunk in client.stream("重构认证模块；删除旧文件前必须确认"):
        if chunk.type == "interaction_request":
            print(f"[{chunk.interaction_kind}] {chunk.content}")
            print("options:", chunk.options)
            await client.submit_interaction(
                request_id=chunk.request_id,
                action="approve",
                content="批准本次变更",
            )
        elif chunk.type == "text_delta":
            print(chunk.content, end="", flush=True)
except InteractionTimeoutError:
    print("等待用户输入超时")
```

交互类型包括 question、confirm 和 feedback。同步客户端无法并发等待交互；需要 Human-in-the-Loop 时使用 `AsyncCodyClient` 或 durable Runtime Approval。

## SDK Interaction 与 Runtime Approval

- SDK Interaction：适合当前进程内的实时 UI，超时会结束本次调用。
- Runtime Approval：持久化为 waiting，释放 worker，可跨进程、跨界面审批后恢复。

涉及长时间等待、服务重启或跨团队审批时，使用 Runtime Approval。
