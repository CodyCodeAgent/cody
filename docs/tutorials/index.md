# 教程路线

教程按“完成一件真实事情”组织。每篇都说明前置条件、可观察结果、关键代码和验证方式；如果你只想查询某个参数或类型，请直接去[指南总览](../guides/index.md)。

<div class="status-row">
  <span class="status-pill">15 篇任务式教程</span>
  <span class="status-pill">覆盖 SDK 到生产 Runtime</span>
  <span class="status-pill">Python 3.10+</span>
</div>

## 路线 A：先把 Agent 跑起来

<div class="track-grid" markdown>

[<span class="track-card__meta">01 · 基础</span><span class="card-title">跑通第一个任务</span><span class="card-copy">安装、配置、执行、读取结构化结果。</span>](01-first-run.md){ .track-card .reveal-card }

[<span class="track-card__meta">02 · 基础</span><span class="card-title">会话与流式输出</span><span class="card-copy">复用 session，处理文本、工具和终态事件。</span>](02-sessions-streaming.md){ .track-card .reveal-card }

[<span class="track-card__meta">03 · 扩展</span><span class="card-title">工具、Skills 与 MCP</span><span class="card-copy">直接调用工具、加载项目规范、连接外部工具服务。</span>](03-tools-skills-mcp.md){ .track-card .reveal-card }

</div>

## 路线 B：构建可编排 Runtime

<div class="track-grid" markdown>

[<span class="track-card__meta">04 · Runtime</span><span class="card-title">启动持久化 Run</span><span class="card-copy">消费 canonical events，获取 Artifact 和稳定 run_id。</span>](04-runtime-run.md){ .track-card .reveal-card }

[<span class="track-card__meta">05 · Workflow</span><span class="card-title">编排并行 Workflow</span><span class="card-copy">节点、边、并行、Join、条件和确定性状态合并。</span>](05-workflow.md){ .track-card .reveal-card }

[<span class="track-card__meta">06 · Team</span><span class="card-title">组织多 Agent 团队</span><span class="card-copy">Specialist role、任务 DAG、并发与 Artifact 聚合。</span>](06-multi-agent.md){ .track-card .reveal-card }

</div>

## 路线 C：完成可恢复质量闭环

<div class="track-grid" markdown>

[<span class="track-card__meta">07 · Control</span><span class="card-title">审批、暂停与恢复</span><span class="card-copy">让 waiting 不占 worker，并从 checkpoint 恢复。</span>](07-approval-recovery.md){ .track-card .reveal-card }

[<span class="track-card__meta">08 · Quality</span><span class="card-title">Quality Gate 修复循环</span><span class="card-copy">测试、lint、review 与有限次数自动返修。</span>](08-quality-gate.md){ .track-card .reveal-card }

[<span class="track-card__meta">09 · Isolation</span><span class="card-title">在 Sandbox 中执行</span><span class="card-copy">文件、网络、环境和资源边界的正确配置。</span>](09-sandbox.md){ .track-card .reveal-card }

</div>

## 路线 D：部署和二次开发

<div class="track-grid" markdown>

[<span class="track-card__meta">10 · Storage</span><span class="card-title">PostgreSQL 与 S3</span><span class="card-copy">把 catalog 与大型 Artifact 拆成生产级存储。</span>](10-production-storage.md){ .track-card .reveal-card }

[<span class="track-card__meta">11 · Operations</span><span class="card-title">CLI、TUI 与 Web 协作</span><span class="card-copy">跨界面观察、审批、恢复和导出运行产物。</span>](11-product-surfaces.md){ .track-card .reveal-card }

[<span class="track-card__meta">12 · Extension</span><span class="card-title">扩展 Runtime</span><span class="card-copy">注册工具、节点、Evaluator、Store 和远程 Sandbox transport。</span>](12-extensions.md){ .track-card .reveal-card }

</div>

## 路线 E：SDK 专题能力

<div class="track-grid" markdown>

[<span class="track-card__meta">13 · Tooling</span><span class="card-title">自定义工具与中间件</span><span class="card-copy">把业务动作注册成工具，并统一做鉴权、改参与输出脱敏。</span>](13-custom-tools.md){ .track-card .reveal-card }

[<span class="track-card__meta">14 · Interaction</span><span class="card-title">多模态与人工交互</span><span class="card-copy">发送截图，在流中接住 question、confirm 与 feedback。</span>](14-multimodal-interaction.md){ .track-card .reveal-card }

[<span class="track-card__meta">15 · Context</span><span class="card-title">记忆、事件与指标</span><span class="card-copy">保存项目知识，监听生命周期事件，导出调用指标。</span>](15-memory-observability.md){ .track-card .reveal-card }

</div>

## 教程与指南的区别

| 你现在想做什么 | 应该看哪里 |
|---|---|
| 从零跑通一个完整场景 | 本教程路线 |
| 查询完整参数、类型和默认值 | [指南](../guides/index.md) |
| 理解信任边界和实现约束 | [架构](../ARCHITECTURE.md)与[Sandbox](../SANDBOX.md) |
| 排查线上 Run | [运行观测与故障处理](../guides/operations.md) |
