# Cody 场景 Demo

这里的示例是可直接运行的完整程序，不是从上下文中截取的伪代码。建议从仓库根目录运行：

```bash
uv sync --all-extras
uv run python -m examples.workflow_parallel
```

## 场景矩阵

| 场景 | 模块 | 默认是否需要外部服务 |
|---|---|---|
| 单次 Coding Agent 任务 | `sdk_single_task` | 模型 API |
| 流式输出与多轮 Session | `sdk_streaming_session` | 模型 API |
| 只读代码审查 | `sdk_read_only_review` | 模型 API |
| 自定义 Tool 与 before hook | `sdk_custom_tool` | 模型 API |
| 图片理解与界面检查 | `sdk_multimodal` | 支持视觉的模型 API |
| SDK 实时问题与确认 | `sdk_interaction` | 模型 API + 人工输入 |
| 直接调用内置 Tool | `sdk_direct_tools` | 否 |
| 项目记忆写入与查询 | `project_memory` | 否 |
| 项目 Skill 发现与读取 | `skill_loading` | 否 |
| 本地 stdio MCP 发现与调用 | `mcp_stdio` | 否 |
| Canonical RunEvent、Artifact 与 Metrics | `runtime_events` | 否 |
| Workflow 并行与 Join | `workflow_parallel` | 否 |
| 多 Agent 能力路由与依赖 DAG | `multi_agent_team` | 否 |
| 持久化审批与新实例恢复 | `approval_resume` | 否 |
| Quality Gate 有界修复循环 | `quality_repair` | 否 |
| 失败重试与历史 Checkpoint Fork | `runtime_retry_fork` | 否 |
| 本地 Sandbox 生命周期与快照 | `sandbox_local` | 否 |
| Remote Sandbox transport 适配 | `remote_sandbox_adapter` | 否，使用演示 transport |
| Docker/Podman Sandbox | `container_sandbox` | 容器 daemon 与本地镜像 |
| SQLite catalog + 外部 Artifact payload | `artifact_storage` | 默认否；S3 模式需要 S3/MinIO |
| PostgreSQL 跨实例状态 | `postgres_shared_state` | PostgreSQL |
| Web Runtime API 客户端 | `web_runtime_client` | Cody Web 与模型 API |

## 无 API Key 的 Demo

下面这些 Demo 使用本地工具或确定性 backend，可以直接运行：

```bash
uv run python -m examples.sdk_direct_tools
uv run python -m examples.project_memory
uv run python -m examples.skill_loading
uv run python -m examples.mcp_stdio
uv run python -m examples.runtime_events
uv run python -m examples.workflow_parallel
uv run python -m examples.multi_agent_team
uv run python -m examples.approval_resume
uv run python -m examples.quality_repair
uv run python -m examples.runtime_retry_fork
uv run python -m examples.sandbox_local
uv run python -m examples.remote_sandbox_adapter
uv run python -m examples.artifact_storage
```

## 真实模型 Demo

密钥只通过环境变量或 secret manager 注入，不要写入源码：

```bash
export CODY_MODEL='deepseek-chat'
export CODY_MODEL_BASE_URL='https://api.deepseek.com/v1'
export CODY_MODEL_API_KEY='your-api-key'

uv run python -m examples.sdk_single_task "解释 Runtime 的执行主链"
uv run python -m examples.sdk_streaming_session
uv run python -m examples.sdk_read_only_review cody/core/runtime
uv run python -m examples.sdk_custom_tool payments
uv run python -m examples.sdk_multimodal ./screenshot.png
uv run python -m examples.sdk_interaction
```

## Sandbox Provider

容器 backend 使用 `--pull=never`，先显式拉取并审查镜像：

```bash
docker pull python:3.13-slim
uv run python -m examples.container_sandbox --engine docker

podman pull python:3.13-slim
uv run python -m examples.container_sandbox --engine podman
```

`remote_sandbox_adapter` 展示的是 provider-neutral contract。真实使用时，把
`DemoRemoteTransport` 的方法替换成供应商 API 调用。

## PostgreSQL 与 S3/MinIO

请使用隔离的测试数据库和 bucket：

```bash
export CODY_POSTGRES_DSN='postgresql://user:password@127.0.0.1:5432/cody_demo'
uv run python -m examples.postgres_shared_state

export CODY_ARTIFACT_BUCKET='cody-demo'
export CODY_ARTIFACT_PREFIX='scenario-demo'
export CODY_S3_ENDPOINT='http://127.0.0.1:9000'
export AWS_ACCESS_KEY_ID='your-access-key'
export AWS_SECRET_ACCESS_KEY='your-secret-key'
uv run python -m examples.artifact_storage --backend s3
```

## Web Runtime API

终端一：

```bash
export CODY_AUTH_API_KEY='local-web-demo-key'
cody-web run --port 8000
```

终端二使用相同的服务鉴权变量：

```bash
export CODY_AUTH_API_KEY='local-web-demo-key'
uv run python -m examples.web_runtime_client \
  --base-url http://127.0.0.1:8000 \
  "分析项目并生成测试建议"
```

更完整的说明与学习顺序见[场景 Demo 指南](../docs/DEMOS.md)。
