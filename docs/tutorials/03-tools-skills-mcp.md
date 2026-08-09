# 03 · 工具、Skills 与 MCP

<div class="tutorial-outcome"><strong>完成后：</strong>你会区分工具、Skill 与 MCP 的职责，并把项目规范和外部能力接到同一 Agent。</div>

## 三者分别解决什么问题

| 扩展 | 作用 | 是否执行代码 |
|---|---|---|
| Tool | 一个可调用动作，例如读文件、搜索、执行命令 | 是 |
| Skill | 告诉 Agent 何时、如何完成一类任务 | 否，它是指令与资源 |
| MCP | 从外部进程或 HTTP 服务发现并调用工具 | 是 |

## 1. 直接调用内置工具

直接调用适合确定性自动化，不经过模型决策：

```python
import asyncio

from cody import AsyncCodyClient


async def main() -> None:
    async with AsyncCodyClient(workdir="/tmp/cody-tutorial") as client:
        result = await client.tool("read_file", {"path": "hello.py"})
        print(result.result)


asyncio.run(main())
```

让模型执行任务时，可以缩小工具面：

```python
result = await client.run(
    "检查实现是否符合要求，不要修改文件",
    include_tools=["read_file", "grep", "glob"],
)
```

## 2. 创建项目 Skill

在目标仓库创建 `.cody/skills/release-check/SKILL.md`：

```markdown
---
name: release-check
description: 发布前检查版本、测试、变更日志和敏感信息。
---

# Release check

1. 检查版本号是否一致。
2. 运行项目规定的测试与静态检查。
3. 检查 CHANGELOG 是否包含当前版本。
4. 搜索可能误提交的 token、私钥和本地配置。
5. 只报告证据，不自动发布。
```

```python
skills = await client.list_skills()
release_skill = await client.get_skill("release-check")
print(skills)
print(release_skill["documentation"])
```

加载优先级是自定义目录、项目 `.cody/skills/`、用户 `~/.cody/skills/`、内置 Skill。详见 [Skills 指南](../SKILLS.md)。

## 3. 接入 MCP

`.cody/config.json` 中注册 stdio server：

```json
{
  "mcp": {
    "servers": [
      {
        "name": "project-tools",
        "transport": "stdio",
        "command": "python",
        "args": ["-m", "my_mcp_server"]
      }
    ]
  }
}
```

```python
async with AsyncCodyClient(
    workdir="/tmp/cody-tutorial",
    auto_start_mcp=True,
) as client:
    tools = await client.mcp_list_tools()
    value = await client.mcp_call("server/tool-name", {"query": "hello"})
```

stdio MCP server 在 Run 的 Sandbox 边界内启动；HTTP MCP client 在可信宿主运行，但 URL 仍受 Runtime 网络策略检查。

## 安全检查

- Tool 权限使用 allow / deny / confirm，而不是在 Prompt 里口头约束。
- Skill 不应包含真实密钥。
- MCP server 视为第三方执行代码，固定版本并限制文件、网络和环境变量。
- 高风险自定义工具必须接入 Runtime policy 和审批链路。
