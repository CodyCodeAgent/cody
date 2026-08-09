# 指南总览

指南按能力域组织，是当前 Cody 3.0 公共行为的查阅入口。历史迭代文档不作为 API 规范。

## Runtime 与生产运行

<div class="doc-grid" markdown>

[:material-timeline-clock-outline: <span class="card-title">Canonical Runtime</span><span class="card-copy">Run 生命周期、Workflow、审批、恢复、多 Agent、Quality Gate 与 Store。</span>](../RUNTIME.md){ .doc-card }

[:material-server-security: <span class="card-title">生产部署</span><span class="card-copy">SQLite/PostgreSQL、S3/MinIO、进程模型、安全边界和上线清单。</span>](production.md){ .doc-card }

[:material-chart-timeline-variant-shimmer: <span class="card-title">观测与故障处理</span><span class="card-copy">Timeline、metrics、checkpoint、artifact、audit 与恢复决策。</span>](operations.md){ .doc-card }

</div>

## 产品入口

<div class="doc-grid" markdown>

[:material-language-python: <span class="card-title">Python SDK</span><span class="card-copy">客户端、Builder、流式、事件、工具、会话和高级注入点。</span>](../SDK.md){ .doc-card }

[:material-console-line: <span class="card-title">CLI</span><span class="card-copy">单次任务、交互会话、Runtime 控制、审批、Artifact 和 Timeline。</span>](../CLI.md){ .doc-card }

[:material-view-dashboard-outline: <span class="card-title">TUI</span><span class="card-copy">全屏终端界面、快捷键、流式显示与会话恢复。</span>](../TUI.md){ .doc-card }

[:material-api: <span class="card-title">HTTP / WebSocket</span><span class="card-copy">Agent、Runtime、会话、审批和实时事件端点。</span>](../API.md){ .doc-card }

</div>

## 配置、安全与扩展

<div class="doc-grid" markdown>

[:material-tune-variant: <span class="card-title">配置参考</span><span class="card-copy">加载优先级、环境变量、权限、安全、重试和上下文压缩。</span>](../CONFIG.md){ .doc-card }

[:material-shield-lock-outline: <span class="card-title">Sandbox</span><span class="card-copy">后端选择、文件/网络策略、secret、资源限制与恢复。</span>](../SANDBOX.md){ .doc-card }

[:material-puzzle-outline: <span class="card-title">Skills</span><span class="card-copy">Agent Skills 开放格式、加载优先级、验证、分发和 SDK 使用。</span>](../SKILLS.md){ .doc-card }

[:material-vector-polyline: <span class="card-title">架构</span><span class="card-copy">组件职责、canonical data flow、依赖方向和信任边界。</span>](../ARCHITECTURE.md){ .doc-card }

[:material-format-list-checks: <span class="card-title">功能清单</span><span class="card-copy">当前能力、安装方式、完整工具表与明确边界。</span>](../FEATURES.md){ .doc-card }

</div>

## 如何判断一项能力是否适合生产

不要只看类名是否存在。至少确认：

1. 执行是否经过 canonical Runtime，而非旁路调用。
2. 状态是否写入 durable store，服务重启后能否恢复。
3. 外部副作用是否有幂等键或收据。
4. secret 是否留在可信宿主且不会进入 event/artifact/audit。
5. 目标部署环境是否真实演练过 Sandbox、数据库和对象存储。

!!! tip "想边做边学？"
    从[教程路线](../tutorials/index.md)开始。教程会把这些能力组合成可验证的端到端场景。
