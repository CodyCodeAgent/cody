# 场景 Demo

<div class="tutorial-outcome"><strong>这里提供什么：</strong>22 个可运行程序，覆盖从 SDK 单次调用到生产 Store 和 Sandbox provider。13 个核心 Demo 不需要模型 API。</div>

教程解释“为什么这样设计”；本页帮助你快速找到一份与真实业务场景接近的可运行骨架。所有源码位于仓库 [`examples/`](https://github.com/CodyCodeAgent/cody/tree/main/examples)。

## 建议学习顺序

```mermaid
flowchart LR
    T[Direct Tools] --> R[Canonical Runtime]
    R --> W[Parallel Workflow]
    W --> M[Multi-Agent]
    M --> A[Approval Resume]
    A --> Q[Quality Repair]
    Q --> S[Sandbox & Stores]
    S --> P[Web / Production]
```

## 1. SDK 与模型调用

| 业务场景 | Demo | 你会看到什么 |
|---|---|---|
| 一次性分析或编码任务 | [`sdk_single_task.py`](https://github.com/CodyCodeAgent/cody/blob/main/examples/sdk_single_task.py) | `run_id`、结果和 Session |
| 聊天式连续任务 | [`sdk_streaming_session.py`](https://github.com/CodyCodeAgent/cody/blob/main/examples/sdk_streaming_session.py) | text/tool/done chunk 与多轮上下文 |
| PR/目录只读审查 | [`sdk_read_only_review.py`](https://github.com/CodyCodeAgent/cody/blob/main/examples/sdk_read_only_review.py) | 仅向模型暴露只读 Tool |
| 业务系统接入 Agent | [`sdk_custom_tool.py`](https://github.com/CodyCodeAgent/cody/blob/main/examples/sdk_custom_tool.py) | 自定义 Tool、参数和 before hook |
| 截图或设计稿分析 | [`sdk_multimodal.py`](https://github.com/CodyCodeAgent/cody/blob/main/examples/sdk_multimodal.py) | 图片 MIME、base64 payload 与 MultimodalPrompt |
| 实时问题与危险操作确认 | [`sdk_interaction.py`](https://github.com/CodyCodeAgent/cody/blob/main/examples/sdk_interaction.py) | interaction_request 与 approve/reject |
| 无模型确定性自动化 | [`sdk_direct_tools.py`](https://github.com/CodyCodeAgent/cody/blob/main/examples/sdk_direct_tools.py) | 直接读文件、glob 和 grep |

真实模型 Demo 使用现有 Cody 配置。最小环境变量：

```bash
export CODY_MODEL='deepseek-chat'
export CODY_MODEL_BASE_URL='https://api.deepseek.com/v1'
export CODY_MODEL_API_KEY='your-api-key'
uv run python -m examples.sdk_single_task "解释这个项目的架构"
```

## 2. Skills 与 MCP

| 场景 | Demo | 外部依赖 |
|---|---|---|
| 项目级操作规范 | [`skill_loading.py`](https://github.com/CodyCodeAgent/cody/blob/main/examples/skill_loading.py) | 无 |
| 本地工具服务 | [`mcp_stdio.py`](https://github.com/CodyCodeAgent/cody/blob/main/examples/mcp_stdio.py) | 无，启动仓库内确定性 MCP server |
| 项目长期知识 | [`project_memory.py`](https://github.com/CodyCodeAgent/cody/blob/main/examples/project_memory.py) | 无，写入、查询并清理隔离的项目记忆 |

```bash
uv run python -m examples.skill_loading
uv run python -m examples.mcp_stdio
uv run python -m examples.project_memory
```

## 3. Canonical Runtime 与 Workflow

| 场景 | Demo | 核心证据 |
|---|---|---|
| 统一事件和产物 | [`runtime_events.py`](https://github.com/CodyCodeAgent/cody/blob/main/examples/runtime_events.py) | RunEvent、Artifact、Checkpoint、Metrics |
| 并行诊断与汇总 | [`workflow_parallel.py`](https://github.com/CodyCodeAgent/cody/blob/main/examples/workflow_parallel.py) | 两分支同时启动并确定性 Join |
| Specialist 团队 | [`multi_agent_team.py`](https://github.com/CodyCodeAgent/cody/blob/main/examples/multi_agent_team.py) | capability routing、任务 DAG、Agent Artifact |
| 人工发布闸门 | [`approval_resume.py`](https://github.com/CodyCodeAgent/cody/blob/main/examples/approval_resume.py) | SQLite waiting、批准、新 Runtime resume |
| 自动修复测试失败 | [`quality_repair.py`](https://github.com/CodyCodeAgent/cody/blob/main/examples/quality_repair.py) | Gate 失败、fallback repair、有限重检 |
| 失败恢复与探索分支 | [`runtime_retry_fork.py`](https://github.com/CodyCodeAgent/cody/blob/main/examples/runtime_retry_fork.py) | failed Run retry、历史 Checkpoint fork 与 lineage |

这五个 Demo 都使用确定性 backend，不调用模型：

```bash
uv run python -m examples.runtime_events
uv run python -m examples.workflow_parallel
uv run python -m examples.multi_agent_team
uv run python -m examples.approval_resume
uv run python -m examples.quality_repair
uv run python -m examples.runtime_retry_fork
```

## 4. Sandbox 场景

| 场景 | Demo | 说明 |
|---|---|---|
| 本地 policy 与 snapshot | [`sandbox_local.py`](https://github.com/CodyCodeAgent/cody/blob/main/examples/sandbox_local.py) | 展示 env 过滤和生命周期；local-policy 本身不是 OS 安全边界 |
| 远程供应商接入 | [`remote_sandbox_adapter.py`](https://github.com/CodyCodeAgent/cody/blob/main/examples/remote_sandbox_adapter.py) | 实现完整 transport contract，不假装存在托管服务 |
| 容器隔离执行 | [`container_sandbox.py`](https://github.com/CodyCodeAgent/cody/blob/main/examples/container_sandbox.py) | Docker/Podman、只读根、禁网、CPU/内存/PID 限制 |

```bash
uv run python -m examples.sandbox_local
uv run python -m examples.remote_sandbox_adapter

docker pull python:3.13-slim
uv run python -m examples.container_sandbox --engine docker
```

Linux Bubblewrap 与 macOS Seatbelt 的配置、可用性探测和 fail-closed 规则见
[Sandbox 指南](SANDBOX.md)。

## 5. Store 与 Artifact

| 场景 | Demo | 说明 |
|---|---|---|
| catalog/payload 分层 | [`artifact_storage.py`](https://github.com/CodyCodeAgent/cody/blob/main/examples/artifact_storage.py) | 默认 filesystem；`--backend s3` 接 S3/MinIO |
| 多进程共享状态 | [`postgres_shared_state.py`](https://github.com/CodyCodeAgent/cody/blob/main/examples/postgres_shared_state.py) | 两个 Store bundle 观察同一 Run 和 Control mutation |

```bash
uv run python -m examples.artifact_storage

export CODY_POSTGRES_DSN='postgresql://user:password@127.0.0.1:5432/cody_demo'
uv run python -m examples.postgres_shared_state
```

生产凭据、TLS、备份、bucket policy 和迁移仍由部署平台负责，参见
[生产部署指南](guides/production.md)。

## 6. Web 与跨界面

[`web_runtime_client.py`](https://github.com/CodyCodeAgent/cody/blob/main/examples/web_runtime_client.py)
从 `POST /runtime/runs` 创建 Run，轮询共享 Store，并读取 canonical timeline：

```bash
# 终端一
export CODY_AUTH_API_KEY='local-demo-key'
cody-web run --port 8000

# 终端二
export CODY_AUTH_API_KEY='local-demo-key'
uv run python -m examples.web_runtime_client "生成仓库测试建议"
```

## 验证策略

- 离线 Demo 会在测试套件中真正执行，而不只是检查语法。
- 外部服务 Demo 至少执行模块导入和 `--help` smoke test。
- 文档 CI 检查本页链接、代码块、生成页面锚点和静态资源。
- Demo 使用临时目录或唯一 Run ID，避免覆盖项目数据。
