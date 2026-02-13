# Cody vs OpenCode — 深度对标分析报告

> 更新时间：2026-02-13
>
> 目标：基于代码实际审查，全面对比 Cody 与 [OpenCode](https://github.com/anomalyco/opencode)（104k Star, MIT），
> 识别功能差距、质量差异和各自优势，制定改进路线。

---

## 目录

1. [项目概况对比](#1-项目概况对比)
2. [功能矩阵对比](#2-功能矩阵对比)
3. [共有功能质量对比](#3-共有功能质量对比)
4. [Cody 的优势](#4-cody-的优势)
5. [Cody 缺失功能清单](#5-cody-缺失功能清单)
6. [改进优先级排序](#6-改进优先级排序)
7. [总结](#7-总结)

---

## 1. 项目概况对比

| 维度 | Cody | OpenCode |
|------|------|----------|
| 语言 | Python 3.9+ | TypeScript（从 Go 重写） |
| AI 框架 | pydantic-ai | AI SDK (Vercel) |
| TUI 框架 | Textual (Python) | OpenTUI (自研 TS + Zig 渲染核心 + SolidJS 响应式) |
| CLI 框架 | Click + Rich | Yargs |
| Server | FastAPI + WebSocket | 自研 HTTP Server + SSE + mDNS |
| 架构模式 | 引擎层 + 多入口（CLI/TUI/RPC/SDK） | Client/Server 分离（Server 可 headless） |
| 接入方式 | CLI / TUI / HTTP Server / Python SDK | TUI / Desktop App / Web / IDE 插件 / SDK (Go + JS/TS) |
| 许可证 | MIT | MIT |
| Stars | — | ~104k |
| 最新版本 | v0.5.0 | v1.1.65 |
| 源码规模 | ~6,400 行 | 数万行（monorepo） |
| 测试 | 418 个 pytest | 完善测试体系 |
| 内置工具数 | 24 个 | 15+ 个 |
| Provider 数 | 5+（通过 pydantic-ai） | 75+（原生适配 10+ 厂商） |
| LSP 语言数 | 3 种（Python/TS-JS/Go） | 30+（自动检测安装） |
| 内置主题 | 0 | 25+（62 色彩属性） |
| 内置 Skill | 5（git/github/docker/npm/python） | 完善 skill 系统 + 自定义 Command |

---

## 2. 功能矩阵对比

### 2.1 AI 工具能力

| 工具类别 | 功能 | Cody | OpenCode | 备注 |
|----------|------|:----:|:--------:|------|
| 文件操作 | read_file | ✅ | ✅ | 两者都支持行范围读取 |
| | write_file | ✅ | ✅ | |
| | edit_file | ✅ | ✅ | 都用精确文本替换 |
| | patch (apply diff) | ✅ | ✅ | |
| | list_directory | ✅ | ✅ | |
| 搜索 | grep | ✅ | ✅ | 都基于正则，都尊重 .gitignore |
| | glob | ✅ | ✅ | |
| | fuzzy search | ✅ | ❌ | Cody 的 `search_files` 有模糊评分 |
| 命令 | bash/exec | ✅ | ✅ | Cody 有命令白名单 + 危险检测 |
| Skill | list/read | ✅ | ✅ | |
| 子代理 | spawn/status/kill | ✅ | ✅ | Cody 异步后台; OpenCode 同步子会话 |
| MCP | list/call | ✅ | ✅ | OpenCode 额外支持 OAuth + 远程 MCP |
| Web | fetch | ✅ | ✅ | |
| | search | ✅ | ✅ | Cody 用 DuckDuckGo，OpenCode 用 Exa |
| LSP | diagnostics | ✅ | ✅ | |
| | definition | ✅ | ✅ | |
| | references | ✅ | ✅ | |
| | hover | ✅ | ✅ | |
| | document symbol | ❌ | ✅ | OpenCode 多出的 LSP 能力 |
| | workspace symbol | ❌ | ✅ | |
| | call hierarchy | ❌ | ✅ | |
| | go to implementation | ❌ | ✅ | |
| 文件历史 | undo/redo | ✅ | ✅ | 质量差距大，见第 3 节 |
| 任务管理 | todo read/write | ✅ | ✅ | |
| 用户交互 | question (结构化提问) | ✅ | ✅ | |

### 2.2 TUI 功能

| 功能 | Cody | OpenCode | 备注 |
|------|:----:|:--------:|------|
| 基础聊天界面 | ✅ | ✅ | |
| 消息气泡/角色区分 | ✅ | ✅ | |
| 流式输出 | ✅ | ✅ | |
| 状态栏 | ✅ (基础) | ✅ (丰富) | OpenCode 显示 token/cost/LSP/MCP 状态 |
| Diff 彩色渲染 | ❌ | ✅ | **缺失** — 文件修改无可视化 |
| 主题系统 | ❌ | ✅ (25+) | **缺失** — 只有硬编码颜色 |
| 命令面板 (Ctrl+P) | ❌ | ✅ | **缺失** — 模糊搜索命令 |
| Leader Key 快捷键 | ❌ | ✅ (50+ 快捷键) | **缺失** |
| 文件 @ 提及 | ❌ | ✅ | **缺失** — 输入框 `@` 搜索文件 |
| ! Shell 快捷执行 | ❌ | ✅ | `!command` 直接执行 shell |
| 外部编辑器 ($EDITOR) | ❌ | ✅ | 长消息编辑 |
| 图片拖拽/粘贴 | ❌ | ✅ | 多平台剪贴板 |
| Token/Cost 显示 | ❌ | ✅ | **缺失** — 用户无法感知开销 |
| Thinking 显示 | ❌ | ✅ | `/thinking` 切换推理可见性 |
| Markdown 渲染 | ❌ (纯文本) | ✅ (完整+语法高亮) | **缺失** |
| Plan Mode | ❌ | ✅ | Tab 切换只读规划模式 |
| Toast 通知 | ❌ | ✅ | |
| 会话列表 UI | ✅ (文本) | ✅ (分组+搜索+导航) | |
| 斜杠命令 | ❌ | ✅ (16+ 内置) | `/new`, `/undo`, `/compact`, `/export` 等 |

### 2.3 会话管理

| 功能 | Cody | OpenCode | 备注 |
|------|:----:|:--------:|------|
| 会话持久化 | ✅ (SQLite) | ✅ (SQLite) | |
| 会话列表/继续 | ✅ | ✅ | |
| 自动标题 | ✅ (取首条消息) | ✅ (LLM 生成) | OpenCode 用隐藏 Agent 生成标题 |
| Context Compaction | ✅ (自动, 截断式) | ✅ (自动, LLM 摘要 + 两阶段裁剪) | Cody 功能可用但质量差距大 |
| 手动触发压缩 | ❌ | ✅ (`/compact`) | |
| Session Fork | ❌ | ✅ (`--fork`) | 从任意消息分叉 |
| Session 分享 | ❌ | ✅ (auto/manual/disabled) | 实时远端同步 |
| Session 导入/导出 | ❌ | ✅ (Markdown/JSON) | `opencode export`, `opencode import` |
| 父子会话导航 | ❌ | ✅ | Leader+Left/Right 导航 |
| Token/Cost 持久化 | ❌ (运行时有，不落盘) | ✅ (每条消息记录 cost) | `opencode stats` 查看统计 |
| Undo/Redo | ✅ (内存栈, 文件级) | ✅ (Git 快照, 消息级) | 质量差距大，见第 3 节 |
| 崩溃恢复 | ⚠️ 完成后才写 DB | ✅ 逐 part 增量写入 | |

### 2.4 配置系统

| 功能 | Cody | OpenCode | 备注 |
|------|:----:|:--------:|------|
| 项目级配置 | ✅ (.cody/config.json) | ✅ (opencode.json) | |
| 全局配置 | ✅ (~/.cody/config.json) | ✅ (~/.config/opencode/) | |
| 远程配置 | ❌ | ✅ (.well-known/opencode) | 组织级默认配置 |
| 配置层级合并 | ✅ (project > global) | ✅ (remote > global > custom > project) | OpenCode 更多层级 |
| 环境变量替换 | ❌ | ✅ ({env:VAR}) | |
| 文件内容引用 | ❌ | ✅ ({file:path}) | |
| 自定义快捷键 | ❌ | ✅ (完全自定义) | |
| 工具逐个启禁 | ❌ | ✅ | |
| 自动更新 | ❌ | ✅ | |
| Debug 模式 | ✅ (--verbose) | ✅ (`opencode debug config`) | |

### 2.5 Provider 支持

| Provider | Cody | OpenCode |
|----------|:----:|:--------:|
| Anthropic (Claude) | ✅ | ✅ |
| OpenAI (GPT) | ✅ (via pydantic-ai) | ✅ |
| Google (Gemini) | ✅ (via pydantic-ai) | ✅ |
| DeepSeek | ✅ (via pydantic-ai) | ✅ |
| GitHub Copilot | ❌ | ✅ (官方合作) |
| Amazon Bedrock | ❌ | ✅ |
| Azure OpenAI | ❌ | ✅ |
| Google Vertex AI | ❌ | ✅ |
| Groq | ❌ | ✅ |
| OpenRouter | ❌ | ✅ |
| Ollama (本地模型) | ❌ | ✅ |
| LM Studio | ❌ | ✅ |
| OpenCode Zen | ❌ | ✅ (自有模型服务) |

> **注**：Cody 通过 pydantic-ai 理论上可接任何 OpenAI 兼容 API，但没有内置发现/配置 UI，用户需手动填 model 字符串。

### 2.6 平台和生态

| 功能 | Cody | OpenCode |
|------|:----:|:--------:|
| CLI | ✅ | ✅ |
| TUI | ✅ | ✅ (OpenTUI, 60fps) |
| HTTP Server (RPC) | ✅ (FastAPI + SSE + WebSocket) | ✅ (REST + SSE) |
| Python SDK | ✅ (sync + async, 自动重试) | ✅ |
| TypeScript/Go SDK | ❌ | ✅ (npm + Go) |
| Desktop App | ❌ | ✅ (Beta) |
| Web 界面 | ❌ | ✅ (`opencode web`) |
| IDE 插件 | ❌ | ✅ (ACP 协议 — VS Code/JetBrains/Neovim/Zed/Emacs) |
| GitHub Actions 集成 | ❌ | ✅ (评论 `/opencode` 触发) |
| Headless 非交互模式 | ✅ (`cody run PROMPT`) | ✅ (`opencode run`) |
| 插件系统 | ❌ | ✅ (npm/local 插件) |
| 自定义 Agent | ❌ | ✅ (Markdown/JSON 定义 .opencode/agents/) |
| 自定义 Command | ❌ | ✅ (Markdown/JSON, 支持参数替换) |

---

## 3. 共有功能质量对比

> 两个项目都有的功能，实现质量对比。

### 3.1 权限系统 — ✅ 已追平

| 维度 | Cody | OpenCode |
|------|------|----------|
| 权限级别 | allow/deny/confirm（三级） | allow/ask/deny（三级） |
| 运行时强制执行 | ✅ 所有 24 个工具均检查 | ✅ |
| 用户可配 | ✅ config.permissions.overrides | ✅ |
| Glob 模式匹配 | ❌ | ✅ (`"git *": "allow"`) |
| Per-Agent 权限 | ❌ | ✅ Agent 级覆盖 |
| Session 级 "always" 审批 | ❌ | ✅ once/always/reject |
| 外部目录控制 | ❌ | ✅ external_directory 权限 |
| Doom loop 保护 | ❌ | ✅ 重复工具调用检测 |

**差距：🟡 中等** — 基础功能已追平，但 OpenCode 在细粒度控制上更强（glob 模式、per-agent、doom loop）。

### 3.2 Context Compaction — ⚠️ 功能可用但质量差距大

| 维度 | Cody | OpenCode |
|------|------|----------|
| 运行时触发 | ✅ 自动（run/run_stream 前检查） | ✅ 自动 |
| Token 估算 | `len(text) // 4`（粗糙） | 使用模型返回的实际 token 数 |
| 压缩方式 | 保留最近 4 条 + 截断摘要 | LLM Agent 生成结构化摘要 |
| 两阶段策略 | ❌ | ✅ 先裁旧工具输出，再 LLM 摘要 |
| 可配置 | ❌ 硬编码阈值 | ✅ auto/manual, buffer 大小, prune 开关 |
| 手动触发 | ❌ | ✅ `/compact` 命令 |

**差距：🟡 中等** — 功能已接入运行时但压缩质量差（截断 vs LLM 摘要），长对话场景 OpenCode 效果好得多。

### 3.3 Undo/Redo — 差距：🔴 巨大

| 维度 | Cody | OpenCode |
|------|------|----------|
| 存储 | 内存 Python list | Git tree 对象 |
| 持久化 | ❌ 进程退出丢失 | ✅ 磁盘持久化 |
| 粒度 | 单个文件修改 | 消息级（回滚到某条消息前的完整状态） |
| 空间效率 | 存 full old/new 内容 | Git content-addressable 自动去重 |
| 恢复能力 | 仅恢复文件内容 | 恢复文件 + 清理消息 + 可反撤销 |

### 3.4 MCP 客户端 — 差距：🟡 中等

| 维度 | Cody | OpenCode |
|------|------|----------|
| 传输 | stdio JSON-RPC | stdio + HTTP (Streamable HTTP) |
| 初始化/工具发现 | ✅ | ✅ |
| 工具调用 | ✅ | ✅ |
| 远程 MCP Server | ❌ | ✅ URL + Headers |
| OAuth 2.0 | ❌ | ✅ 自动 Dynamic Client Registration |
| 权限集成 | ✅ mcp_call 需 CONFIRM | ✅ glob 模式控制 MCP 工具 |
| 错误恢复 | ✅ 进程死亡检测 + BrokenPipe 处理 | ✅ |
| 协议版本 | 2024-11-05 | 最新 |

### 3.5 LSP 客户端 — 差距：🔴 巨大

| 维度 | Cody | OpenCode |
|------|------|----------|
| 语言数 | 3 (Python, TS/JS, Go) | 30+ (几乎所有主流语言) |
| 能力 | 4 (diagnostics, definition, references, hover) | 9+ (+ documentSymbol, workspaceSymbol, callHierarchy, implementation) |
| 自动检测安装 | ❌ 需手动安装 LSP Server | ✅ |
| 自定义 LSP Server | ❌ | ✅ 指定 command + extensions |
| 配置选项 | ❌ | ✅ env, initializationOptions, disabled |

### 3.6 会话存储 — 差距：🟡 中等

| 维度 | Cody | OpenCode |
|------|------|----------|
| 后端 | SQLite | SQLite |
| 数据丰富度 | role + content | token/cost/model/tool states/snapshots |
| 崩溃恢复 | ⚠️ 流式完成后才写 DB | ✅ 逐 part 增量写入 |
| Schema 迁移 | ❌ | ✅ 内置迁移系统 |

### 3.7 子代理系统 — 差距：🟢 基本持平，各有优劣

| 维度 | Cody | OpenCode |
|------|------|----------|
| 代理类型 | 4 (code/research/test/generic) | 2 内置 (General/Explore) + 自定义 |
| 异步执行 | ✅ 后台并发（fire-and-forget） | ❌ 同步阻塞（子会话） |
| 并发控制 | ✅ Semaphore(5) | ✅ |
| 超时 | ✅ 300s | ✅ 可配 |
| 自定义 Agent | ❌ | ✅ Markdown/JSON 定义 |
| 父子会话 | ❌ | ✅ 有导航 |

> **Cody 的优势**：子代理异步后台执行，支持并发 fire-and-forget；OpenCode 当前是同步的（[Issue #5887](https://github.com/anomalyco/opencode/issues/5887) 在讨论异步化）。

### 3.8 Streaming — ✅ 基本持平

| 维度 | Cody | OpenCode |
|------|------|----------|
| 后端 | pydantic-ai stream_text() | AI SDK stream |
| 传输 | SSE (FastAPI) + WebSocket | SSE (REST) |
| SDK 支持 | ✅ Python async iterator | ✅ Go + JS/TS SDK |
| 心跳 | ❌ | ✅ 30s heartbeat |
| 增量消息写入 | ❌ 完成后才写 DB | ✅ 逐 part 写入 |

---

## 4. Cody 的优势

并非全是差距。Cody 在以下方面做得比 OpenCode 好：

| 优势 | Cody | OpenCode |
|------|------|----------|
| **工具安全** | ✅ 命令白名单 + 危险模式检测（`rm -rf /`、fork bomb、`dd if=`） | ❌ 无内置检测 |
| **审计日志** | ✅ SQLite 持久化，按事件类型/时间查询 | ❌ 无专门审计系统 |
| **模糊文件搜索** | ✅ `search_files` 有多级评分（exact > starts > contains） | ❌ 无对应工具 |
| **子代理异步** | ✅ 后台并发，fire-and-forget | ❌ 当前同步阻塞 |
| **速率限制** | ✅ 滑动窗口限流器 | ❌ 无内置限流 |
| **认证系统** | ✅ HMAC-SHA256 token + OAuth + API Key | 外部 OAuth 依赖 |
| **工具数量** | 24 个内置工具 | 15+ 个内置工具 |
| **架构** | "引擎做厚壳子做薄"，三入口共享 core | Client/Server 分离更彻底 |
| **测试覆盖** | 418 个 pytest，每模块对应测试文件 | 完善测试 |
| **Python 生态** | Python SDK (sync+async)，适合 Python 项目集成 | 主打 TS/Go 生态 |
| **RPC Server** | FastAPI + OpenAPI spec + WebSocket，可直接嵌入其他系统 | REST + SSE |
| **沙箱安全** | ❌ 但有白名单 + 审计 | ❌ 无沙箱，[Issue #12674](https://github.com/anomalyco/opencode/issues/12674) 讨论中 |

> **关键差异化**：Cody 定位是"可嵌入的 AI 编程引擎"（RPC Server + Python SDK），
> OpenCode 定位是"全功能终端 IDE"（TUI + Desktop + Web + IDE 插件）。两者面向不同场景。

---

## 5. Cody 缺失功能清单

按影响程度排序，仅列出 Cody 完全没有的功能：

### 5.1 TUI 体验

| 功能 | 影响 | 建议实现方式 |
|------|------|-------------|
| Diff 彩色渲染 | 🔴 高 | `rich.syntax` 或 `difflib` + 主题色渲染 |
| Markdown 渲染 | 🔴 高 | `rich.markdown` 渲染助手回复 |
| Token/Cost 显示 | 🔴 高 | StatusLine 添加 token 计数（pydantic-ai 有 usage 数据） |
| 主题系统 | 🟡 中 | 先 3-5 个常见主题（Catppuccin/Dracula/Nord） |
| 命令面板 | 🟡 中 | Textual OptionList + 搜索过滤 |
| 文件 @ 提及 | 🟡 中 | fuzzywuzzy + Textual Autocomplete |
| 斜杠命令 | 🟡 中 | `/new`, `/undo`, `/compact` 等 |
| Plan Mode | 🟡 中 | Tab 切换只读模式 |
| Thinking 可见性 | 🟡 中 | 检查 pydantic-ai 是否暴露 reasoning |
| 外部编辑器 | 🟢 低 | subprocess.run + app.suspend |
| 图片支持 | 🟢 低 | Kitty/sixel 协议 |
| Toast 通知 | 🟢 低 | Textual Notification |

### 5.2 会话管理

| 功能 | 影响 | 建议 |
|------|------|------|
| Session Fork | 🟡 中 | 克隆 session + messages，记录 parent_id |
| Session 导入/导出 | 🟡 中 | Markdown/JSON 格式 |
| Token/Cost 持久化 | 🟡 中 | messages 表加 token/cost 列 |
| 流式增量写入 | 🟡 中 | 逐 part 写 DB 防崩溃丢数据 |
| Session 分享 | 🟢 低 | 远端同步，后期实现 |

### 5.3 配置与自定义

| 功能 | 影响 | 建议 |
|------|------|------|
| 自定义快捷键 | 🟡 中 | 配置文件定义 keybinds |
| 自定义 Agent | 🟡 中 | 支持 Markdown/JSON 定义 Agent |
| 自定义 Command | 🟡 中 | Markdown 文件 + 参数替换 |
| 远程配置 | 🟢 低 | .well-known/cody 端点 |
| 环境变量替换 | 🟢 低 | {env:VAR} 语法 |
| 工具逐个启禁 | 🟢 低 | config.tools.disabled 列表 |

### 5.4 生态

| 功能 | 影响 | 建议 |
|------|------|------|
| 更多 LSP 语言 | 🟡 中 | 优先加 Rust、Java、C/C++ |
| TypeScript/Go SDK | 🟡 中 | 拓展非 Python 用户群 |
| IDE 插件 | 🟡 中 | ACP 协议或 LSP 方式 |
| GitHub Actions 集成 | 🟡 中 | PR 评论触发 |
| Desktop App | 🟢 低 | Electron/Tauri 包装 |
| Web 界面 | 🟢 低 | 已有 RPC Server，前端包装即可 |
| 插件系统 | 🟢 低 | 后期实现 |

---

## 6. 改进优先级排序

### P0 — ✅ 已完成（2026-02-13）

| # | 任务 | 状态 | 改动 |
|---|------|:----:|------|
| 1 | 权限系统接入运行时 | ✅ | `tools.py` — 所有可变工具 `_check_permission()` |
| 2 | Context Compaction 接入 runner | ✅ | `runner.py` — `_compact_history_if_needed()` 自动调用 |
| 3 | FEATURES.md 修正 | ✅ | 删除 6 个虚假工具，修正 CLI 命令名 |
| 4 | 依赖修正 | ✅ | 删 aiofiles，prompt_toolkit → optional [repl] |
| 5 | MCP 版本号 + 废弃 API | ✅ | 版本 → 2024-11-05，get_running_loop() |
| 6 | 4 个内置 Skill | ✅ | github/docker/npm/python |
| 7 | MCP 错误恢复增强 | ✅ | BrokenPipe 处理 + 进程死亡检测 |
| 8 | todo_write/todo_read 工具 | ✅ | AI 自管理任务清单 |
| 9 | question 工具 | ✅ | 结构化用户提问 |

### P1 — TUI 体验核心差距

| # | 任务 | 工作量 | 理由 |
|---|------|--------|------|
| 10 | **Diff 彩色渲染** | 中 | 文件修改无可视化 |
| 11 | **Markdown 渲染** | 中 | 纯文本输出体验差 |
| 12 | **Token/Cost 显示** | 小 | 用户无法控制开销 |
| 13 | **斜杠命令** | 中 | 功能发现性差 |
| 14 | **文件 @ 提及** | 中 | 高频需求 |
| 15 | **流式增量写入** | 中 | 防崩溃丢数据 |

### P2 — 持续改进

| # | 任务 | 工作量 | 理由 |
|---|------|--------|------|
| 16 | **主题系统** | 中 | 个性化体验 |
| 17 | **LLM 驱动 Compaction** | 中 | 压缩质量 |
| 18 | **Undo 持久化** | 大 | 重启后 undo 全丢 |
| 19 | **Session Fork/导出** | 中 | 探索性编程 |
| 20 | **更多 LSP 语言** | 中 | 语言覆盖不足 |
| 21 | **命令面板 Ctrl+P** | 中 | 功能发现 |
| 22 | **Plan Mode** | 中 | 安全规划模式 |
| 23 | **自定义 Agent/Command** | 中 | 灵活性 |
| 24 | **权限细化**（glob/per-agent） | 中 | 与 OpenCode 看齐 |
| 25 | **Token/Cost 持久化** | 小 | 用量统计 |

### P3 — 长远规划

| # | 任务 |
|---|------|
| 26 | 远程 MCP Server + OAuth 支持 |
| 27 | 外部编辑器 / 图片支持 |
| 28 | GitHub Actions 集成 |
| 29 | IDE 插件 (ACP 协议) |
| 30 | TypeScript/Go SDK |
| 31 | Desktop App / Web 界面 |
| 32 | 插件系统 |
| 33 | Session 分享 |
| 34 | 远程配置 |

---

## 7. 总结

### 当前状态

经过 P0 修复，Cody 的**核心引擎**（工具执行、权限、MCP、LSP、子代理、Context Compaction、审计）已全部接通运行时，基础功能可用。

### 主要差距

| 维度 | 差距程度 | 说明 |
|------|---------|------|
| TUI 体验 | 🔴 巨大 | 无 diff、无主题、无 Markdown、无命令面板、无 @ 提及 |
| 会话智能 | 🟡 中等 | 压缩质量差（截断 vs LLM 摘要）、无 fork/导出、无 cost 持久化 |
| Undo/Redo | 🔴 巨大 | 内存不持久 vs Git 快照持久 |
| LSP 覆盖 | 🔴 巨大 | 3 vs 30+ 语言，4 vs 9+ 能力 |
| Provider | 🟡 中等 | 理论可扩展但无 UI 和原生适配 |
| 生态 | 🔴 巨大 | 无 Desktop/Web/IDE 插件/GitHub Actions |

### Cody 的核心优势

| 优势 | 说明 |
|------|------|
| 工具安全 | 命令白名单 + 危险检测 + 审计日志，OpenCode 均无 |
| 子代理异步 | 后台并发 fire-and-forget，OpenCode 是同步阻塞 |
| Python 可嵌入性 | RPC Server + Python SDK，适合作为引擎嵌入其他系统 |
| 速率限制 | 内置滑动窗口限流 |
| 模糊搜索 | search_files 多级评分，OpenCode 无对应工具 |

### 战略定位

- **Cody**："可嵌入的 AI 编程引擎" — 引擎做厚、壳子做薄，适合 Python 生态集成
- **OpenCode**："全功能终端 AI IDE" — 极致 TUI 体验 + 多平台 + 庞大生态

两者面向不同使用场景。Cody 不需要在 TUI 体验上追赶 OpenCode 的全部功能，
但 **P1 的 6 项 TUI 基础体验**（diff/markdown/token/斜杠命令/@ 提及/增量写入）
是独立使用时的底线，建议优先补齐。
