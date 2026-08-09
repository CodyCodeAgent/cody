---
template: home.html
hide:
  - navigation
  - toc
  - feedback
---

## 先选一条路线

教程和指南承担不同任务：教程带你完成真实闭环，指南用于准确查阅能力、配置和边界。

<div class="doc-grid" markdown>

[:material-school-outline: <span class="card-title">按任务学习</span><span class="card-copy">15 篇教程，从首次运行一直做到 Workflow、多 Agent、恢复、Sandbox、生产存储和 SDK 专题。</span>](tutorials/index.md){ .doc-card .reveal-card }

[:material-book-open-page-variant-outline: <span class="card-title">按能力查阅</span><span class="card-copy">Runtime、SDK、CLI、Web、配置、安全、部署和扩展的完整指南。</span>](guides/index.md){ .doc-card .reveal-card }

[:material-vector-polyline: <span class="card-title">理解架构</span><span class="card-copy">看清 canonical execution path、数据流、信任边界和扩展依赖方向。</span>](ARCHITECTURE.md){ .doc-card .reveal-card }

</div>

## 一条权威执行主链

<div class="runtime-flow">
  <div class="runtime-flow__step"><strong>Run</strong><span>身份、预算、权限与持久化生命周期</span></div>
  <div class="runtime-flow__step"><strong>Workflow</strong><span>顺序、并行、条件、Join、Fallback 与嵌套</span></div>
  <div class="runtime-flow__step"><strong>Execution</strong><span>Agent、工具、审批、Quality Gate 与 Sandbox</span></div>
  <div class="runtime-flow__step"><strong>RunEvent</strong><span>Timeline、Checkpoint、Artifact、Audit 与恢复</span></div>
</div>

CLI、TUI、Web 与 SDK 不各自维护运行状态；它们都是 Canonical Runtime 的不同入口和视图。

## 生产能力，不只是接口占位

<div class="capability-grid" markdown>

[:material-timeline-clock-outline: <span class="card-title">Durable Runtime</span><span class="card-copy">Run / Step / Event / Checkpoint / Approval / Artifact / Audit 使用稳定关联标识。</span>](RUNTIME.md){ .capability-card .reveal-card }

[:material-source-branch: <span class="card-title">Workflow 与多 Agent</span><span class="card-copy">并发调度、确定性合并、任务 DAG、局部失败和有界重试。</span>](tutorials/05-workflow.md){ .capability-card .reveal-card }

[:material-shield-lock-outline: <span class="card-title">Sandbox 边界</span><span class="card-copy">Seatbelt、Bubblewrap、Docker/Podman 与 provider-neutral Remote adapter。</span>](SANDBOX.md){ .capability-card .reveal-card }

[:material-database-cog-outline: <span class="card-title">生产存储</span><span class="card-copy">SQLite 单机开发，PostgreSQL 多进程 catalog，S3/MinIO 承载大型 Artifact。</span>](tutorials/10-production-storage.md){ .capability-card .reveal-card }

[:material-check-decagram-outline: <span class="card-title">Quality Gate</span><span class="card-copy">测试、lint、风险检查与受预算和次数限制的诊断—修复循环。</span>](tutorials/08-quality-gate.md){ .capability-card .reveal-card }

[:material-radar: <span class="card-title">治理与观测</span><span class="card-copy">Actor、权限、预算、审批、脱敏、指标和完整执行时间线。</span>](guides/operations.md){ .capability-card .reveal-card }

</div>

## 60 秒开始

=== "Python SDK"

    ```bash
    pip install cody-ai
    export CODY_MODEL='your-model-id'
    export CODY_MODEL_BASE_URL='https://your-provider.example/v1'
    export CODY_MODEL_API_KEY='your-api-key'
    ```

    ```python
    import asyncio
    from cody import AsyncCodyClient

    async def main() -> None:
        async with AsyncCodyClient(workdir="/path/to/project") as client:
            result = await client.run("修复失败的测试，并说明验证结果")
            print(result.output)

    asyncio.run(main())
    ```

=== "CLI / TUI"

    ```bash
    pip install 'cody-ai[cli,tui]'
    cody config setup
    cody run "修复失败的测试，并说明验证结果"
    # 或进入全屏终端
    cody tui
    ```

=== "Web"

    ```bash
    pip install 'cody-ai[web]'
    cody-web run --port 8000
    # 打开 http://localhost:8000
    ```

!!! note "模型接入"
    Cody 使用 OpenAI-compatible Chat Completions 接口。模型 ID 和 Base URL 必须以你所用端点的当前文档为准；API Key 只通过环境变量或 secret manager 注入。

## 当前边界

我们会明确区分“已实现”与“需要部署方提供”的能力：

- Remote Sandbox 是 transport/handle 适配层，不是 Cody 托管的远程沙箱服务。
- PostgreSQL、S3/MinIO、Docker/Podman 和 Bubblewrap 需要对应外部服务或系统依赖。
- `local-policy` 提供路径、命令和环境策略，但不是 OS 级隔离。
- 自定义 Python 扩展运行在可信宿主中，不受 guest Sandbox 隔离。
- 企业 OAuth/SSO 不是内置产品能力；Web 内置鉴权是 API Key，可通过 Auth extension 接入外部身份系统。

[查看完整功能与边界](FEATURES.md){ .md-button }
[开始系统教程](tutorials/index.md){ .md-button .md-button--primary }
