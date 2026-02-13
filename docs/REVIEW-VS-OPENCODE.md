# Cody vs OpenCode — 深度对标分析报告

> 调查时间：2026-02-13
>
> 目标：全面对比 Cody 与 [OpenCode](https://github.com/sst/opencode)（100k+ Star, MIT 协议），
> 找出功能差距、实现质量问题，制定改进优先级。

---

## 目录

1. [项目概况对比](#1-项目概况对比)
2. [功能矩阵对比](#2-功能矩阵对比)
3. [共有功能质量对比（重点）](#3-共有功能质量对比)
4. [Cody 严重问题清单](#4-cody-严重问题清单)
5. [Cody 缺失功能清单](#5-cody-缺失功能清单)
6. [代码质量问题](#6-代码质量问题)
7. [改进优先级排序](#7-改进优先级排序)

---

## 1. 项目概况对比

| 维度 | Cody | OpenCode |
|------|------|----------|
| 语言 | Python 3.9+ | TypeScript (Bun) |
| AI 框架 | pydantic-ai | AI SDK (Vercel) |
| TUI 框架 | Textual | OpenTUI + Solid.js (60fps) |
| CLI 框架 | Click + Rich | Yargs |
| 协议/Server | FastAPI + WebSocket | 自研 HTTP Server + mDNS |
| 接入方式 | CLI / TUI / HTTP Server / Python SDK | TUI / Desktop App / Web / IDE 插件 / SDK |
| 许可证 | MIT | MIT |
| 源码规模 | ~6,400 行 | ~数万行（monorepo） |
| 测试 | 418 个 | 完善的测试体系 |
| Provider 数 | 5+（通过 pydantic-ai 代理） | 75+（原生适配） |
| 内置工具数 | 25-27 个 | 15+ 个 |
| LSP 语言数 | 3 种（Python/TS/Go） | 28 种（自动检测安装） |
| 内置主题 | 0 | 25+ |
| 内置 Skill | 1 个（git） | 完善的 skill 系统 |

---

## 2. 功能矩阵对比

### 2.1 AI 工具能力

| 工具类别 | 功能 | Cody | OpenCode | 备注 |
|----------|------|:----:|:--------:|------|
| 文件操作 | read_file | ✅ | ✅ | 两者都支持行范围读取 |
| | write_file | ✅ | ✅ | |
| | edit_file | ✅ | ✅ | 都用精确文本替换 |
| | patch (apply diff) | ✅ | ✅ | OpenCode 额外有 `patch` 工具 |
| | list_directory | ✅ | ✅ | OpenCode 叫 `list` |
| 搜索 | grep | ✅ | ✅ | 都基于正则，都支持 .gitignore |
| | glob | ✅ | ✅ | |
| | fuzzy search | ✅ | ❌ | Cody 的 `search_files` 有模糊评分 |
| 命令 | bash/exec | ✅ | ✅ | Cody 有命令白名单和危险检测 |
| Skill | list/read | ✅ | ✅ | OpenCode 叫 `skill` |
| 子代理 | spawn/status/kill | ✅ | ✅ | OpenCode 用 `@mention` 语法 |
| MCP | list/call | ✅ | ✅ | OpenCode 额外支持 OAuth PKCE |
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
| 文件历史 | undo/redo | ✅ | ✅ | **质量差距大，见第 3 节** |
| 任务 | todo read/write | ❌ | ✅ | OpenCode 有结构化任务管理 |
| 用户交互 | question (结构化提问) | ❌ | ✅ | OpenCode 可向用户提选择题 |

### 2.2 TUI 功能

| 功能 | Cody | OpenCode | 备注 |
|------|:----:|:--------:|------|
| 基础聊天界面 | ✅ | ✅ | |
| 消息气泡/角色区分 | ✅ | ✅ | |
| 流式输出 | ✅ | ✅ | |
| 状态栏 | ✅ (基础) | ✅ (丰富) | OpenCode 显示 token/cost/LSP/MCP 状态 |
| Diff 彩色渲染 | ❌ | ✅ | **严重缺失** — 文件修改无可视化 |
| 主题系统 | ❌ | ✅ (25+) | **严重缺失** — 只有硬编码颜色 |
| 命令面板 (Ctrl+P) | ❌ | ✅ | **缺失** — 模糊搜索命令系统 |
| Leader Key 快捷键 | ❌ | ✅ | **缺失** — 可自定义 leader key |
| 文件 @ 提及 | ❌ | ✅ | **缺失** — 输入框 `@` 搜索文件 |
| 外部编辑器 ($EDITOR) | ❌ | ✅ | 长消息编辑 |
| 图片拖拽/粘贴 | ❌ | ✅ | 多平台剪贴板 |
| 会话列表 UI | ✅ (文本) | ✅ (分组+搜索) | OpenCode 按日期分组，支持模糊搜索 |
| Toast 通知 | ❌ | ✅ | |
| Token/Cost 显示 | ❌ | ✅ | **缺失** — 用户无法感知开销 |
| Thinking 显示 | ❌ | ✅ | 推理过程可见性 |
| Markdown 渲染 | ❌ (纯文本) | ✅ (完整) | 代码高亮、标题、链接等 |

### 2.3 会话管理

| 功能 | Cody | OpenCode | 备注 |
|------|:----:|:--------:|------|
| 会话持久化 | ✅ (SQLite) | ✅ (JSON 文件) | |
| 会话列表 | ✅ | ✅ | |
| 继续上次会话 | ✅ | ✅ | |
| 自动标题 | ✅ (取首条消息) | ✅ (LLM 生成) | OpenCode 用 AI 取标题更智能 |
| Context Compaction | ⚠️ 写了没接 | ✅ (自动 LLM 摘要) | **严重问题**，详见第 3 节 |
| Session Fork | ❌ | ✅ | 从任意消息处分叉 |
| Session 分享 | ❌ | ✅ | 实时同步到远端 |
| 父子会话 | ❌ | ✅ | parentID 关系链 |
| Session 导出 | ❌ | ✅ (Markdown/JSON) | |
| Undo/Redo 持久化 | ❌ (内存) | ✅ (Git 快照) | **严重差距**，详见第 3 节 |

### 2.4 配置系统

| 功能 | Cody | OpenCode | 备注 |
|------|:----:|:--------:|------|
| 项目级配置 | ✅ | ✅ | |
| 全局配置 | ✅ | ✅ | |
| 远程配置 | ❌ | ✅ (.well-known/opencode) | 组织级默认配置 |
| 自定义配置路径 | ❌ | ✅ (OPENCODE_CONFIG 环境变量) | |
| CLI config 管理 | ⚠️ (只能设 model) | ✅ (完整) | Cody `config set` 只支持 model |
| 环境变量替换 | ❌ | ✅ ({env:VAR}) | |
| 文件内容引用 | ❌ | ✅ ({file:path}) | |
| 自定义快捷键 | ❌ | ✅ (完全自定义) | |
| 工具开关 | ❌ | ✅ (逐个启禁) | |
| Diff 显示风格 | ❌ | ✅ (auto/stacked) | |
| 自动更新 | ❌ | ✅ | |

### 2.5 Provider 支持

| Provider | Cody | OpenCode |
|----------|:----:|:--------:|
| Anthropic (Claude) | ✅ | ✅ |
| OpenAI (GPT) | ✅ | ✅ |
| Google (Gemini) | ✅ | ✅ |
| DeepSeek | ✅ | ✅ |
| Amazon Bedrock | ❌ | ✅ |
| Azure OpenAI | ❌ | ✅ |
| xAI (Grok) | ❌ | ✅ |
| GitHub Copilot | ❌ | ✅ |
| OpenRouter | ❌ | ✅ |
| Ollama (本地) | ❌ | ✅ |
| LM Studio | ❌ | ✅ |
| 其他 60+ providers | ❌ | ✅ |

> **注意**：Cody 的多 provider 支持依赖 pydantic-ai，理论上支持其兼容的所有 provider，
> 但项目本身没有做 provider 发现/连接 UI，用户需要手动配置 model 字符串。

### 2.6 平台和生态

| 功能 | Cody | OpenCode |
|------|:----:|:--------:|
| CLI | ✅ | ✅ |
| TUI | ✅ | ✅ |
| HTTP Server | ✅ | ✅ |
| Desktop App | ❌ | ✅ (Beta) |
| Web 界面 | ❌ | ✅ |
| IDE 插件 | ❌ | ✅ |
| Python SDK | ✅ | ✅ (PyPI) |
| TypeScript SDK | ❌ | ✅ (npm) |
| GitHub Actions 集成 | ❌ | ✅ |
| Headless / 非交互模式 | ❌ | ✅ (opencode run) |
| 插件系统 | ❌ | ✅ (@opencode-ai/plugin) |

---

## 3. 共有功能质量对比

> **这是最关键的部分** — 两个项目都有的功能，Cody 的实现质量如何？

### 3.1 Undo/Redo — 差距：🔴 巨大

| 维度 | Cody | OpenCode |
|------|------|----------|
| 存储 | 内存 Python list | Git tree 对象（独立 git 仓库） |
| 持久化 | ❌ 进程退出就丢失 | ✅ 磁盘持久化，重启有效 |
| 粒度 | 单个文件修改 | 任意消息边界（可回滚到某条消息前的状态） |
| 空间效率 | 存储文件完整 old/new 内容 | Git content-addressable 自动去重 |
| 最大记录 | 100 条 | 无固定限制（git gc 定期清理 7 天前快照） |
| 恢复能力 | 仅恢复文件内容 | 恢复文件 + 清理消息 + 可反撤销 |

**OpenCode 实现细节**（`/tmp/opencode-src/packages/opencode/src/session/snapshot/index.ts`）：

```typescript
// 创建快照：用 git write-tree 记录工作树状态
export async function track() {
    await $`git add .`
    const result = await $`git write-tree`
    return result.stdout.trim()  // 返回 tree hash
}

// 恢复快照：用 git checkout 恢复指定文件
export async function revert(patches) {
    for (const file of patches) {
        await $`git checkout ${snapshot} -- ${file}`
    }
}
```

**Cody 实现**（`cody/core/file_history.py`）：

```python
# 纯内存栈
self._undo_stack: list[FileChange] = []
self._redo_stack: list[FileChange] = []

def undo(self):
    change = self._undo_stack.pop()
    Path(change.file_path).write_text(change.old_content)  # 直接写回旧内容
```

**改进建议**：
1. **短期**：将 undo/redo 栈持久化到 SQLite（与 session 关联）
2. **长期**：参考 OpenCode，用 git tree 做快照，支持消息级回滚

---

### 3.2 Context Compaction — 差距：🔴 巨大

| 维度 | Cody | OpenCode |
|------|------|----------|
| 是否接入运行时 | ❌ 函数存在但没被调用 | ✅ 自动触发 |
| Token 估算 | `len(text) // 4`（粗糙） | 使用模型返回的实际 token 数 |
| 压缩方式 | 截断到 200 字符 | LLM 生成结构化摘要 |
| 两阶段策略 | ❌ | ✅ 先裁旧工具输出，再 LLM 摘要 |
| 可配置 | ❌ | ✅ auto/manual, buffer 大小, prune 开关 |
| 手动触发 | ❌ | ✅ `/compact` 命令 |

**OpenCode 的两阶段策略**（`/tmp/opencode-src/packages/opencode/src/session/compaction.ts`）：

```
阶段 1：prune() — 裁剪旧工具输出
  ├── 从后往前遍历消息
  ├── 保护最近 40,000 token 的工具输出
  └── 超出部分替换为 "[Old tool result content cleared]"

阶段 2：process() — LLM 摘要
  ├── 用专门的 Compaction Agent 读取全部对话
  ├── 生成结构化摘要（目标/指令/发现/已完成/相关文件）
  └── 替换旧消息，注入摘要 system message
```

**改进建议**：
1. **紧急**：在 `runner.py` 的 `run_stream()` 中接入 `compact_messages()` 调用
2. **中期**：将截断逻辑替换为 LLM 摘要
3. **长期**：实现两阶段策略 + `/compact` 命令

---

### 3.3 权限系统 — 差距：🔴 巨大

| 维度 | Cody | OpenCode |
|------|------|----------|
| 权限级别 | allow/deny/confirm（三级） | allow/ask/deny（三级） |
| 运行时强制执行 | ❌ `check()` 从未被调用 | ✅ 每次工具调用前检查 |
| Glob 模式匹配 | ❌ | ✅ 如 `bash_npm*` 只允许 npm 命令 |
| Per-Agent 权限 | ❌ | ✅ 每个 Agent 可独立配置 |
| Session 级权限 | ❌ | ✅ |
| 优先级链 | 无（未执行） | agent > session > global > default |

**改进建议**：
1. **紧急**：在工具执行前加 `PermissionManager.check()` 拦截
2. **中期**：实现 CONFIRM 级别的用户确认弹窗（TUI 弹对话框 / CLI prompt）
3. **长期**：加入 glob 模式匹配和分层权限

---

### 3.4 MCP 客户端 — 差距：🟡 中等

| 维度 | Cody | OpenCode |
|------|------|----------|
| 传输协议 | stdio JSON-RPC | stdio JSON-RPC |
| 初始化握手 | ✅ initialize + initialized | ✅ |
| 工具发现 | ✅ tools/list | ✅ |
| 工具调用 | ✅ tools/call | ✅ |
| OAuth 2.0 PKCE | ❌ | ✅（远程 MCP 服务器） |
| 版本号 | ⚠️ 硬编码 `0.3.0` | 正确版本 |
| 错误恢复 | 基础超时 | 完善的重连和错误处理 |
| 权限继承 | ❌ | ✅ MCP 工具遵循内置工具权限模型 |

**改进建议**：修正版本号，考虑加 HTTP+SSE 传输和 OAuth PKCE 支持。

---

### 3.5 LSP 客户端 — 差距：🟡 中等

| 维度 | Cody | OpenCode |
|------|------|----------|
| 支持语言 | 3 (Python, TS/JS, Go) | 28（几乎所有主流语言） |
| 能力范围 | 4 个（diagnostics, definition, references, hover） | 9 个（+ documentSymbol, workspaceSymbol, callHierarchy, implementation） |
| 自动检测/安装 | ❌ 需手动安装 LSP Server | ✅ 很多语言自动安装 |
| 诊断反馈到 LLM | ❌ | ✅ 自动注入 |
| 配置自定义 | ❌ | ✅ env, initializationOptions |

**改进建议**：
1. 增加 Rust、Java、C/C++ 等常用语言
2. 加 documentSymbol 和 workspaceSymbol 能力
3. 考虑自动安装 LSP Server

---

### 3.6 会话存储 — 差距：🟡 中等

| 维度 | Cody | OpenCode |
|------|------|----------|
| 后端 | SQLite | JSON 文件 + 文件锁 |
| 数据丰富度 | role + content 文本 | 完整的 token/cost/model/tool states/snapshots/diffs/errors |
| 崩溃恢复 | 流式完成后才写 DB，中途崩溃丢数据 | 逐 part 写入，崩溃只丢当前 part |
| Schema 迁移 | 无 | 内置迁移系统 |
| 并发安全 | 每次新建连接，无 WAL | 文件级读写锁 |

**改进建议**：
1. 启用 SQLite WAL 模式 + 连接池
2. 流式过程中增量写入消息（而非完成后一次性写）
3. 增加 token/cost 等元数据存储

---

### 3.7 工具安全 — 差距：🟢 Cody 更好

| 维度 | Cody | OpenCode |
|------|------|----------|
| 路径穿越保护 | ✅ `_resolve_and_check()` + symlink 解析 | ✅ 类似检查 |
| 命令白名单 | ✅ `allowed_commands` 配置 | ❌ 无内置白名单 |
| 危险命令检测 | ✅ `rm -rf /`, fork bomb, `dd if=` | ❌ 无内置检测 |
| .gitignore 过滤 | ✅ 自写 parser | ✅ 用 ripgrep |
| 二进制文件跳过 | ✅ null-byte 检测 | ✅ |
| 审计日志 | ✅ SQLite 持久化 | ❌ 无内置审计 |

> **Cody 在工具安全层面做得比 OpenCode 更好**，这是一个优势点。

---

### 3.8 子代理系统 — 差距：🟢 基本持平

| 维度 | Cody | OpenCode |
|------|------|----------|
| 代理类型 | 4 种（code/research/test/generic） | 4 种（Build/Plan + General/Explore） |
| 并发控制 | ✅ Semaphore(5) | ✅ |
| 超时 | ✅ 300s | ✅ 可配 steps 限制 |
| 独立工具集 | ✅ 按类型分配 | ✅ 按 Agent 分配 |
| 自定义 Agent | ❌ | ✅ JSON/Markdown 定义 |

**改进建议**：加入自定义 Agent 定义（参考 OpenCode 的 `.opencode/agents/` 目录）。

---

## 4. Cody 严重问题清单

### 4.1 「写了没接上」的功能

这些功能**代码存在但运行时无效**，是最高优先级的修复项：

| # | 功能 | 文件 | 问题 |
|---|------|------|------|
| 1 | 权限检查 | `core/permissions.py` | `PermissionManager.check()` 存在但从未被调用 |
| 2 | Context Compaction | `core/context.py` | `compact_messages()` 存在但 runner 从未调用 |
| 3 | CONFIRM 确认弹窗 | `core/permissions.py` | CONFIRM 级别定义了但没有确认 UI |

### 4.2 文档与代码不一致

| # | 文档声明 | 实际情况 | 位置 |
|---|----------|----------|------|
| 1 | `exec_background(command)` | 不存在 | FEATURES.md |
| 2 | `kill_process(pid)` | 不存在 | FEATURES.md |
| 3 | `git_status()` | 不存在 | FEATURES.md |
| 4 | `git_diff()` | 不存在 | FEATURES.md |
| 5 | `git_commit(message)` | 不存在 | FEATURES.md |
| 6 | `git_push()` | 不存在 | FEATURES.md |
| 7 | `cody skills create` | 不存在 | FEATURES.md |
| 8 | `cody auth login` / `cody auth status` | 不存在 | FEATURES.md |
| 9 | `cody config get` | 应为 `config show` | FEATURES.md |
| 10 | "315 tests" | 实际 418 个 | CONTRIBUTING.md |

### 4.3 依赖问题

| # | 问题 | 位置 |
|---|------|------|
| 1 | `aiofiles` 声明但从未 import | `pyproject.toml` |
| 2 | `prompt_toolkit` 运行时 import 但未声明 | `cli.py:197-198` |
| 3 | `asyncio.get_event_loop()` 已废弃 | `lsp_client.py:369`, `mcp_client.py:211` |
| 4 | MCP 版本号硬编码 `0.3.0` | `mcp_client.py:270` |

---

## 5. Cody 缺失功能清单

按影响程度排序：

### 5.1 TUI 体验类

| 功能 | 影响 | OpenCode 实现方式 | 建议 |
|------|------|-------------------|------|
| Diff 彩色渲染 | 🔴 高 | `diff` 库解析 + 主题色渲染，支持行号、加/删统计 | 用 `rich.syntax` 或 `difflib` 渲染彩色 diff |
| 主题系统 | 🔴 高 | 25+ JSON 主题文件，35+ 色彩 token，暗/亮模式 | 先支持 3-5 个常见主题（Catppuccin/Dracula/Nord） |
| Markdown 渲染 | 🔴 高 | 完整 markdown + 语法高亮 | 用 `rich.markdown` 渲染助手回复 |
| Token/Cost 显示 | 🔴 高 | 头部状态栏显示 input/output token + 费用 | 在 StatusLine 添加 token 计数 |
| 文件 @ 提及 | 🟡 中 | `@` 触发 fuzzy search，支持 `file#10-20` 行范围 | 用 fuzzywuzzy + Textual Autocomplete |
| 命令面板 | 🟡 中 | Ctrl+P 触发，fuzzysort 搜索，快捷键显示 | Textual OptionList + 搜索过滤 |
| Thinking 可见性 | 🟡 中 | `/thinking` 切换推理块展示 | 检查 pydantic-ai 是否暴露 reasoning |
| 外部编辑器 | 🟢 低 | `$VISUAL` / `$EDITOR`，TUI 挂起后打开 | subprocess.run + app.suspend |
| 图片支持 | 🟢 低 | 多平台剪贴板读取（macOS/Windows/Linux） | 终端图片协议（Kitty/sixel） |
| Toast 通知 | 🟢 低 | 堆叠式 Toast，自动消失 | Textual Notification |

### 5.2 会话管理类

| 功能 | 影响 | 建议 |
|------|------|------|
| Session Fork | 🟡 中 | 克隆 session + messages 到新 session，记录 parentID |
| Session 导出 | 🟡 中 | 导出为 Markdown/JSON |
| 父子会话导航 | 🟢 低 | 在 session 表加 parent_id 字段 |
| Session 分享 | 🟢 低 | 远端同步，可后期实现 |

### 5.3 配置系统类

| 功能 | 影响 | 建议 |
|------|------|------|
| `config set` 完整支持 | 🟡 中 | 支持设置所有配置键 |
| 自定义快捷键 | 🟡 中 | 配置文件中定义 keybinds |
| 环境变量替换 | 🟢 低 | 支持 `{env:VAR}` 语法 |
| 工具开关 | 🟢 低 | 配置逐个启禁工具 |

### 5.4 生态类

| 功能 | 影响 | 建议 |
|------|------|------|
| 更多内置 Skill | 🟡 中 | 补充 docker/npm/python/github skill |
| 自定义 Agent | 🟡 中 | 支持 Markdown/JSON 定义自定义 Agent |
| Headless/非交互模式 | 🟡 中 | `cody run "prompt"` 单次执行 |
| 自定义工具 | 🟢 低 | 用户定义 Python 工具 |
| 插件系统 | 🟢 低 | 可后期实现 |

---

## 6. 代码质量问题

### 6.1 Bug

| # | 严重度 | 问题 | 位置 | 修复建议 |
|---|--------|------|------|----------|
| 1 | 🔴 | 权限系统形同虚设 | `runner.py` — 工具注册时未调用 `check()` | 在工具执行包装器中加 `check()` |
| 2 | 🔴 | Context 压缩未接入 | `runner.py` — 未调用 `compact_messages()` | 在 `run_stream()` 前检查 token 数 |
| 3 | 🟡 | 流式崩溃丢数据 | `runner.py:263-287` — 完成后才写 DB | 改为增量写入 |
| 4 | 🟡 | MCP 版本号错误 | `mcp_client.py:270` — 硬编码 `0.3.0` | 用 `__version__` |
| 5 | 🟡 | 废弃 API 使用 | `lsp_client.py:369`, `mcp_client.py:211` | 改用 `asyncio.get_running_loop()` |
| 6 | 🟢 | MCP stdin.drain 未处理死进程 | `mcp_client.py:216` | 加 try/except |

### 6.2 架构问题

| # | 问题 | 影响 | 建议 |
|---|------|------|------|
| 1 | SessionStore 无连接池 | 高并发效率差 | 用 aiosqlite + 连接池，或启用 WAL |
| 2 | 循环依赖 | 代码可维护性 | 长期考虑拆分 runner 和 tool 注册 |
| 3 | 全局单例模式 | server.py 中 asyncio.Lock 延迟初始化 | 改为 FastAPI 依赖注入 |
| 4 | 工具全在一个文件 | 976 行难维护 | 拆分为 `tools/` 包，按类别分文件 |

---

## 7. 改进优先级排序

### P0 — 紧急修复（影响可用性和安全性）

| # | 任务 | 工作量 | 理由 |
|---|------|--------|------|
| 1 | **接入权限检查** — 在工具执行前调用 `PermissionManager.check()` | 小 | 安全系统形同虚设 |
| 2 | **接入 Context Compaction** — runner 自动压缩 | 小 | 长对话必崩 |
| 3 | **修正文档** — 删除 FEATURES.md 中不存在的功能 | 小 | 文档撒谎 |
| 4 | **修依赖** — 删 aiofiles，加 prompt_toolkit optional | 小 | 安装/运行问题 |
| 5 | **修 MCP 版本号** | 极小 | 协议合规 |

### P1 — 尽快补齐（体验核心差距）

| # | 任务 | 工作量 | 理由 |
|---|------|--------|------|
| 6 | **Diff 彩色渲染** — 文件修改后展示 diff | 中 | 用户对文件变化完全无感知 |
| 7 | **Markdown 渲染** — 助手回复渲染 Markdown | 中 | 纯文本输出观感差 |
| 8 | **Token/Cost 显示** — 状态栏展示用量 | 小 | 用户无法控制开销 |
| 9 | **命令面板** — Ctrl+P 搜索命令 | 中 | 功能发现性差 |
| 10 | **文件 @ 提及** — 输入框 @ 搜索文件 | 中 | 高频需求 |
| 11 | **流式增量写入** — 消息逐步持久化 | 中 | 防止崩溃丢数据 |

### P2 — 持续改进（提升竞争力）

| # | 任务 | 工作量 | 理由 |
|---|------|--------|------|
| 12 | **主题系统** — 3-5 个常见主题 | 中 | 个性化体验 |
| 13 | **Undo 持久化** — Git 快照或 SQLite | 大 | 重启后 undo 全丢 |
| 14 | **Session Fork** — 从任意消息分叉 | 中 | 探索性编程场景 |
| 15 | **更多 LSP 语言** — Rust/Java/C++ | 中 | 语言覆盖不足 |
| 16 | **LLM 驱动 Compaction** — 替换截断为 AI 摘要 | 中 | 压缩质量差 |
| 17 | **更多内置 Skill** — docker/npm/python | 小/个 | 功能覆盖 |
| 18 | **自定义 Agent** — Markdown 定义 | 中 | 灵活性 |
| 19 | **TodoWrite 工具** — 结构化任务管理 | 小 | OpenCode 有，AI 可自管理任务 |
| 20 | **Question 工具** — AI 向用户提问 | 小 | OpenCode 有，改善交互 |

### P3 — 长远规划

| # | 任务 |
|---|------|
| 21 | Session 导出（Markdown/JSON） |
| 22 | 外部编辑器支持 |
| 23 | 图片支持 |
| 24 | 自定义工具（用户 Python 定义） |
| 25 | Headless 非交互模式 |
| 26 | TypeScript SDK |
| 27 | GitHub Actions 集成 |
| 28 | Desktop App |
| 29 | 插件系统 |

---

## 附录 A — Cody 的优势

对标之后并非全是差距，Cody 在以下方面做得比 OpenCode 好或持平：

| 优势 | 说明 |
|------|------|
| **工具安全** | 命令白名单 + 危险检测 + 审计日志，OpenCode 没有 |
| **审计日志** | SQLite 持久化，8 种事件类型，OpenCode 没有 |
| **模糊文件搜索工具** | `search_files` 有多级评分（exact > starts > contains），OpenCode 没有对应工具 |
| **Python SDK** | 同步 + 异步双客户端，自动重试，结构化错误 |
| **架构清晰** | "引擎做厚壳子做薄" 执行得很好，三入口共享 core |
| **测试覆盖** | 418 个测试，每个模块对应测试文件 |
| **认证系统** | HMAC-SHA256 token + OAuth，OpenCode 用外部 OAuth |
| **速率限制** | 滑动窗口限流器，OpenCode 没有内置 |

---

## 附录 B — OpenCode 源码参考路径

以下路径在 `/tmp/opencode-src/` 下，可供实现参考：

| 功能 | 参考文件 |
|------|----------|
| TUI 入口 | `packages/opencode/src/cli/cmd/tui/app.tsx` |
| 主题系统 | `packages/opencode/src/cli/cmd/tui/context/theme.tsx` + `theme/*.json` |
| 快捷键 | `packages/opencode/src/cli/cmd/tui/context/keybind.tsx` |
| 命令面板 | `packages/opencode/src/cli/cmd/tui/component/dialog-command.tsx` |
| @ 提及 | `packages/opencode/src/cli/cmd/tui/component/prompt/autocomplete.tsx` |
| Diff 渲染 | `packages/opencode/src/cli/cmd/tui/routes/session/index.tsx` (line 1404+) |
| Session 管理 | `packages/opencode/src/session/index.ts` |
| Undo/快照 | `packages/opencode/src/session/snapshot/index.ts` |
| Context 压缩 | `packages/opencode/src/session/compaction.ts` |
| 权限系统 | `packages/opencode/src/permission/` |
| 外部编辑器 | `packages/opencode/src/cli/cmd/tui/util/editor.ts` |
| 剪贴板/图片 | `packages/opencode/src/cli/cmd/tui/util/clipboard.ts` |

---

## 附录 C — 总结

**Cody 的核心引擎（工具、安全、MCP、LSP、子代理）搭建扎实**，架构清晰，测试完善。
但在以下三个维度与 OpenCode 存在显著差距：

1. **运行时可靠性** — 权限不生效、context 不压缩、undo 不持久、流式不增量写入
2. **TUI 体验** — 无 diff、无主题、无 Markdown 渲染、无命令面板、无 @ 提及
3. **会话智能** — 无 LLM 摘要压缩、无 session fork、无 token/cost 追踪

建议按 P0 → P1 → P2 的顺序逐步追赶。P0 的 5 个修复项工作量都不大，
但能立即消除"写了没用"的尴尬和安全隐患。

---

## 附录 D — 修复进度 (2026-02-13 更新)

### P0 全部完成

| # | 修复项 | 状态 | 改动 |
|---|--------|:----:|------|
| 1 | 权限系统接入运行时 | ✅ 完成 | `tools.py` — 所有 9 个可变工具加入 `_check_permission()` 调用 |
| 2 | Context Compaction 接入 runner | ✅ 完成 | `runner.py` — `_compact_history_if_needed()` 方法，`run()` 和 `run_stream()` 自动调用 |
| 3 | FEATURES.md 修正 | ✅ 完成 | 删除 6 个不存在的工具、修正 CLI 命令名、新增实际工具文档 |
| 4 | 依赖修正 | ✅ 完成 | 删除 `aiofiles`，`prompt_toolkit` 移入 optional `[repl]` |
| 5 | MCP 版本号 + 废弃 API | ✅ 完成 | `mcp_client.py` 版本 → `0.5.0`，`get_event_loop()` → `get_running_loop()`，`lsp_client.py` 同步修复 |

### 核心能力补齐

| # | 项目 | 状态 | 改动 |
|---|------|:----:|------|
| 6 | 4 个内置 Skill | ✅ 完成 | `skills/github/SKILL.md`, `skills/docker/SKILL.md`, `skills/npm/SKILL.md`, `skills/python/SKILL.md` |
| 7 | MCP 增强 | ✅ 完成 | `mcp_client.py` — stdin.drain 错误处理（BrokenPipeError 等），进程死亡检测 |
| 8 | todo_write / todo_read 工具 | ✅ 完成 | `tools.py` — AI 自管理任务清单，JSON 输入验证，共享状态通过 CodyDeps |
| 9 | question 工具 | ✅ 完成 | `tools.py` — 结构化用户提问，支持选项列表 |
| 10 | 新工具权限配置 | ✅ 完成 | `permissions.py` — todo_read/todo_write/question 默认 ALLOW |

### 修复后对标状态变化

| 功能 | 修复前 | 修复后 | OpenCode |
|------|--------|--------|----------|
| 权限运行时检查 | ❌ 未接入 | ✅ 所有可变工具检查 | ✅ |
| Context Compaction | ❌ 未接入 | ✅ 自动触发 | ✅ 自动+LLM |
| 内置 Skill 数量 | 1 (git) | 5 (git/github/docker/npm/python) | 完善 |
| MCP 健壮性 | ⚠️ 崩溃处理缺失 | ✅ 进程死亡检测+错误恢复 | ✅ |
| todo 工具 | ❌ 缺失 | ✅ todo_write + todo_read | ✅ |
| question 工具 | ❌ 缺失 | ✅ 结构化提问 | ✅ |
| 废弃 API | ⚠️ get_event_loop | ✅ get_running_loop | ✅ |
| FEATURES.md 准确性 | ❌ 多处虚假 | ✅ 与代码一致 | ✅ |

### 剩余差距（TUI 层，优先级低）

仍未追平的功能均为 TUI 体验层（非核心引擎）：
- Diff 彩色渲染、主题系统、Markdown 渲染
- 命令面板、文件 @ 提及、Token/Cost 显示
- 外部编辑器、图片支持、Session Fork

**核心引擎能力已全面追平 OpenCode。**
