# Cody 项目综合审查报告

> 审查日期：2026-03-20 | 版本：v1.11.0

---

## 一、项目架构评估

### 1.1 整体架构

Cody 采用 **Hub-and-Spoke（中心辐射）** 分层架构，`AgentRunner` 为中枢：

```
                    ┌─────────┐
                    │  CLI    │
                    └────┬────┘
                         │
┌─────────┐    ┌─────────┴──────────┐    ┌─────────┐
│  TUI    │───▸│   SDK (client.py)  │◂───│   Web   │
└─────────┘    └─────────┬──────────┘    └─────────┘
                         │
               ┌─────────▾──────────┐
               │  Core / AgentRunner │
               │    (runner.py)      │
               └─────────┬──────────┘
                         │
        ┌────────┬───────┼───────┬────────┐
        ▾        ▾       ▾       ▾        ▾
     Tools    Session  Memory   MCP     LSP
   (29 个)   (SQLite) (File)  Client  Client
```

**评价：架构清晰，分层合理。** Core 不依赖任何上层模块，工具注册声明式，依赖注入通过 `CodyDeps` 统一管理。

### 1.2 模块划分

| 模块 | 文件数 | 代码行数 | 职责 | 评分 |
|------|--------|---------|------|------|
| `core/` | 24 | ~5,928 | 框架核心引擎 | ★★★★★ |
| `core/tools/` | 16 | ~2,500 | 29 个工具实现 | ★★★★★ |
| `sdk/` | 7 | ~2,960 | Python SDK | ★★★★☆ |
| `cli/` | 8 | ~850 | 命令行实现 | ★★★☆☆ |
| `tui/` | 3 | ~700 | 终端 UI | ★★★☆☆ |
| `web/backend/` | 22 | ~4,415 | Web API | ★★★★☆ |
| `web/src/` | ~13 | — | React 前端 | ★★★☆☆ |
| `tests/` | 28 | — | 673+ 测试 | ★★★★☆ |
| `docs/` | 10 | — | 项目文档 | ★★★★☆ |

### 1.3 代码抽象亮点

1. **声明式工具注册** — 在 `registry.py` 的列表中添加函数即可，无需修改 runner
2. **依赖注入** — `CodyDeps` 数据类集中管理 14 个依赖，工具通过 `ctx.deps` 访问
3. **懒加载** — `__init__.py` 使用 `__getattr__()` 延迟导入 70+ 公开符号
4. **Builder 模式** — SDK 提供 `Cody().workdir().model().build()` 流式 API
5. **策略模式** — 上下文压缩支持截断和 LLM 两种策略
6. **流式事件** — 14 种事件类型覆盖完整的 Agent 生命周期

---

## 二、Prompt 体系审查

### 2.1 当前 Prompt 架构

系统共有 **10 个 Prompt 来源**，按注入顺序：

1. **Base Persona**（`runner.py:402-423`）— 角色定义 + 子 Agent 并行指导
2. **Project Instructions**（合并 `~/.cody/CODY.md` + 项目 `CODY.md`）
3. **Project Memory**（跨会话学习记忆，按分类注入）
4. **Available Skills XML**（Agent Skills 标准格式）
5. **Dynamic MCP Tools**（每次运行动态生成）

子 Agent 有 4 套独立 Prompt：code / research / test / generic。

### 2.2 Prompt 优化建议

#### 问题 1：Base Persona 过于简略

**现状：** 主 Agent Prompt 仅 ~15 行，缺少关键行为约束。

**建议补充：**
- **输出格式规范** — 何时使用 Markdown、代码块、列表
- **错误处理指导** — 工具调用失败时的重试策略和降级方案
- **安全约束** — 明确禁止的操作（如删除根目录、修改系统文件）
- **代码质量要求** — 保持现有代码风格、不引入不必要的依赖
- **任务完成标准** — 什么算"完成"（测试通过？编译成功？）
- **上下文管理** — 指导 Agent 在长对话中主动使用 `save_memory`

```
建议结构：
1. 角色定义（你是谁）
2. 能力边界（你能/不能做什么）
3. 行为准则（怎么做）
4. 输出规范（怎么表达）
5. 安全约束（什么不能做）
6. 工具使用指南（优先级和策略）
```

#### 问题 2：子 Agent Prompt 缺少协作指导

**现状：** 子 Agent 只知道自己的职责，不知道如何与主 Agent 交互。

**建议补充：**
- 输出格式要求（结构化摘要，方便主 Agent 聚合）
- 错误上报规范（什么情况下提前终止并报告）
- 范围约束（不要超出指定目录/文件范围）

#### 问题 3：Context Compaction Prompt 可以更精准

**现状：** 通用的"300 words or fewer"摘要。

**建议优化：**
- 区分不同任务类型（coding vs research vs debugging）的压缩策略
- 保留工具调用链（哪些工具成功/失败）
- 保留文件修改记录（哪些文件被写入/编辑）
- 添加"进行到哪一步了"的进度标记

#### 问题 4：Skills Prompt 缺少使用策略

**现状：** 只列出可用 Skills，没有指导何时/如何使用。

**建议补充：**
- 自动匹配规则（检测到 Dockerfile → 自动加载 docker skill）
- 明确 `read_skill` 的调用时机（不要每次都加载所有 skills）

#### 问题 5：缺少"思考链"指导

**建议补充：**
- 在处理复杂任务时，先制定计划再执行
- 在修改代码前，先阅读相关代码理解上下文
- 在运行命令前，先检查当前环境状态

---

## 三、项目待完善点

### 3.1 核心功能缺失

| 优先级 | 项目 | 说明 |
|--------|------|------|
| **P0** | 插件系统 | 无法通过代码扩展框架行为（只有 Skills 和 MCP），需要类似 opencode 的事件钩子插件机制 |
| **P0** | 多 Provider 支持 | 当前仅通过 pydantic-ai，opencode 支持 75+ Provider，需要更灵活的模型接入层 |
| **P1** | Client/Server 分离 | 当前 SDK 是 in-process，无法像 opencode 那样通过 HTTP API 让多客户端（IDE 插件、移动端）共享同一 Agent |
| **P1** | IDE 插件 | 无 VS Code / Zed / JetBrains 插件 |
| **P1** | LSP 自动安装 | 当前需要手动安装语言服务器，opencode 有 30+ 语言服务器自动检测安装 |
| **P2** | 自定义 Agent | 无法通过配置文件定义新的 Agent 类型和行为 |
| **P2** | 自定义 Commands | 缺少像 opencode 那样的 Markdown 模板命令系统 |
| **P2** | 会话分享 | 无法生成可分享的会话链接 |
| **P2** | Desktop 应用 | 无 Electron 桌面应用 |

### 3.2 SDK 层待完善

| 项目 | 说明 |
|------|------|
| 批量执行 | 不支持并行运行多个 Prompt |
| 重试机制 | 瞬态失败（网络超时等）没有自动重试 + 指数退避 |
| 速率限制元数据 | 客户端无法获取剩余配额信息 |
| Builder 验证 | `build()` 前不检查 model 是否为空 |
| 并发流安全 | 多个并发 `stream()` 调用的 `_current_run` 追踪可能竞态 |

### 3.3 CLI 层待完善

| 项目 | 说明 |
|------|------|
| 管道支持 | 不支持 `git diff \| cody run "review this"` 的 stdin 输入 |
| 输出格式 | 不支持 `--format json/markdown` 输出 |
| 批量模式 | 不支持从文件读取多个任务 |
| Dry-run | 无法预览 Agent 将执行的操作 |
| 超时配置 | 无 `--timeout` CLI 参数 |
| 工具直接调用 | 无 `cody tool read_file path` 命令 |

### 3.4 TUI 层待完善

| 项目 | 说明 |
|------|------|
| 命令面板 | 缺少 Ctrl+Shift+P 命令面板 |
| 会话切换 | 无法在 TUI 内快速切换会话 |
| 文件浏览 | 缺少侧边栏文件浏览器 |
| 设置界面 | 无法在 TUI 内修改配置 |
| 主题切换 | 无亮色/暗色主题切换 |
| 导出对话 | 无法保存对话历史到文件 |

### 3.5 Web 层待完善

| 项目 | 说明 |
|------|------|
| WebSocket 心跳 | 无 keepalive/ping-pong 机制 |
| 请求去重 | 相同请求会重复执行 |
| Rate Limit Headers | 客户端看不到 `X-RateLimit-Remaining` |
| 熔断器指标 API | 无法查询熔断器状态 |
| Agent 生命周期事件 | 无法通过 WebSocket 监控 Agent 启动/关闭 |
| 文件编辑器 | 前端缺少代码编辑器组件 |
| 移动端适配 | 前端无响应式布局 |

### 3.6 测试覆盖缺口

| 区域 | 问题 |
|------|------|
| SDK 集成测试 | `run()`/`stream()` 缺少端到端集成测试 |
| CLI 流渲染 | 流式渲染未测试实际 Agent 输出 |
| TUI 交互 | 取消、键盘输入、消息展示缺少测试 |
| Web WebSocket | 并发连接测试不足 |
| MCP 集成 | 动态服务器添加未测试 |
| 错误场景 | 网络中断、无效路径、权限拒绝等边缘场景 |
| 性能测试 | 无负载/压力测试 |

---

## 四、与 opencode 对比分析

### 4.1 基本信息对比

| 维度 | Cody | opencode |
|------|------|----------|
| 语言 | Python | TypeScript (Bun) |
| Stars | — | ~126k |
| 架构 | In-process SDK + 独立 Web 后端 | **Client/Server（HTTP API + OpenAPI Spec）** |
| 模型支持 | pydantic-ai | **75+ Provider（via AI SDK + Models.dev）** |
| LSP | 需手动安装 | **30+ 语言服务器自动安装** |
| 工具数量 | 29 | 15 |
| 客户端 | CLI + TUI + Web | **TUI + Web + Desktop(Electron) + IDE 插件** |
| 文件 | CODY.md | AGENTS.md |

### 4.2 opencode 有而 Cody 缺少的功能

#### (1) 插件系统（Plugin System）★★★★★

opencode 有完整的 JS/TS 插件系统，支持事件钩子：
- 可监听 11 类事件（command, file, tool, session, LSP, message, permission, server, shell, TUI, todo）
- 可定义**自定义工具**（通过 `tool` helper）
- 放在 `.opencode/plugins/` 或作为 npm 包加载

**Cody 现状：** 只有 Skills（Markdown 指令）和 MCP（外部服务），无法通过代码扩展框架行为。

**建议：** 这是最大的差距。需要设计 Python 插件系统，支持事件钩子和自定义工具注册。

#### (2) Client/Server 架构 ★★★★★

opencode 启动时同时运行 TUI + HTTP Server（端口 4096），提供：
- **OpenAPI 3.1 规范**的完整 REST API
- mDNS 局域网发现
- HTTP Basic 认证
- 多客户端共享同一 Agent 实例

**Cody 现状：** SDK 是 in-process，Web 后端是独立进程。CLI/TUI 不能与 Web 共享 Agent 状态。

**建议：** 考虑统一为 Server 模式，CLI/TUI 也通过 HTTP/WebSocket 连接本地 Server。

#### (3) 自定义 Commands ★★★★☆

opencode 支持在 `.opencode/commands/` 中定义 Markdown 模板命令：
- 支持 `$ARGUMENTS`、`$1`、`@filename`、`` !`command` `` 占位符
- 可在 TUI 中通过 `/command_name` 调用

**Cody 现状：** 无此功能。Skills 是只读指令，不是可参数化的命令模板。

#### (4) 自定义 Agent 类型 ★★★★☆

opencode 可通过 JSON 配置定义新 Agent：
- 指定 mode（plan/build）、model、temperature、tool 权限、自定义 prompt
- 可引用 Markdown 文件作为系统提示

**Cody 现状：** 子 Agent 类型硬编码（code/research/test/generic），用户无法自定义。

#### (5) 细粒度 Bash 权限 ★★★☆☆

opencode 支持 glob 模式的命令权限：
```json
"bash": {
  "git status *": "allow",
  "rm -rf *": "deny",
  "npm *": "ask"
}
```

**Cody 现状：** `SecurityConfig.allowed_commands` 是简单的字符串列表 + 黑名单模式。

#### (6) 会话分享 ★★★☆☆

opencode 可生成可分享的会话链接。

**Cody 现状：** 无此功能。

#### (7) IDE 插件 ★★★☆☆

opencode 有 VS Code 和 Zed 扩展。

**Cody 现状：** 无 IDE 集成。

### 4.3 Cody 有而 opencode 没有的优势

| 优势 | 说明 |
|------|------|
| **更多工具** | 29 vs 15，多了 patch、search_files、sub-agent 控制、MCP 管理、undo/redo、memory、todo |
| **跨会话记忆** | ProjectMemoryStore 可积累项目知识，自动注入 Prompt |
| **审计日志** | 完整的 AuditLogger 系统（SQLite） |
| **熔断器** | CircuitBreaker 防止无限循环和成本失控 |
| **速率限制** | 内置 RateLimiter |
| **文件历史** | undo/redo 跟踪文件修改 |
| **上下文压缩** | 支持 LLM 和截断两种策略 |
| **Python 生态** | 对 Python 开发者更友好，pip install 即用 |

### 4.4 差距优先级矩阵

```
                    影响力
                    高 │  插件系统    Client/Server
                      │  多Provider
                      │
                      │  自定义Agent  自定义Commands
                      │  IDE插件
                      │
                    低 │  会话分享    Bash权限glob
                      │  Desktop
                      └──────────────────────────
                        低            高
                              实现难度
```

**建议优先级：**
1. 多 Provider 支持（影响力高 + 难度适中）
2. 插件系统（影响力高 + 难度高，但是核心竞争力）
3. 自定义 Agent / Commands（影响力中 + 难度低）
4. Client/Server 统一（影响力高 + 难度高，长期架构演进）

---

## 五、综合建议路线图

### 短期（v1.12 - v1.13）

- [ ] **Prompt 优化** — 按上述建议增强 Base Persona 和子 Agent Prompt
- [ ] **多 Provider 支持** — 抽象模型接入层，支持 OpenAI、Google、DeepSeek 等
- [ ] **自定义 Commands** — `.cody/commands/` 目录下的 Markdown 模板命令
- [ ] **自定义 Agent 类型** — 通过配置文件定义新 Agent
- [ ] **CLI 增强** — stdin 管道输入、`--format json`、`--timeout`
- [ ] **细粒度 Bash 权限** — glob 模式命令权限

### 中期（v1.14 - v1.16）

- [ ] **插件系统** — Python 插件 + 事件钩子 + 自定义工具注册
- [ ] **LSP 自动安装** — 检测项目语言后自动安装对应 language server
- [ ] **SDK Builder 验证** — 构建时校验必填参数
- [ ] **并发安全** — 修复 metrics 竞态、增加并发流测试
- [ ] **Web 增强** — WebSocket 心跳、Rate Limit Headers、熔断器指标 API
- [ ] **TUI 增强** — 命令面板、会话切换、文件浏览

### 长期（v2.0）

- [ ] **Client/Server 统一架构** — CLI/TUI 也通过本地 Server 与 Core 交互
- [ ] **IDE 插件** — VS Code / JetBrains 扩展
- [ ] **会话分享** — 可分享链接 + 导出
- [ ] **Desktop 应用** — Electron 或 Tauri
- [ ] **移动端适配** — 响应式 Web UI

---

## 六、总结

**Cody 是一个架构优秀的 AI Coding Agent 框架**，在核心引擎设计（工具注册、依赖注入、流式事件、安全控制）方面做得很好。代码质量高，无循环依赖，无 TODO/FIXME 技术债。

**主要差距在生态层面：**

1. **可扩展性** — 缺少插件系统，用户无法通过代码扩展框架
2. **模型生态** — Provider 支持有限
3. **客户端生态** — 无 IDE 插件和 Desktop 应用
4. **架构统一性** — CLI/TUI/Web 没有统一的 Server 层

Prompt 体系结构合理但内容偏简略，建议参考 Claude Code 的详细程度进行增强。

核心引擎是 Cody 的最大优势——做好它，然后通过插件系统和多 Provider 支持让生态繁荣起来。
