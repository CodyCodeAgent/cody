# Cody 项目代码审查报告（v2）

**审查日期**: 2026-03-08
**审查版本**: v1.7.4
**审查范围**: 全部源码（core/、sdk/、cli/、tui/、web/backend/、web/src/）+ 文档 + 测试
**审查人**: AI Code Review (Claude Opus 4.6)

---

## 一、总体评价

**综合评分: 8.5 / 10**

Cody 是一个架构设计精良、工程质量上乘的 AI Coding Agent 框架。项目从 v1.0 到 v1.7.4 的演进中，持续修复了先前审查中发现的问题（数据库连接管理、SSRF 防护、Config 深度合并、API Key 持久化安全等），代码成熟度进一步提高。以下是各维度的分项评分：

| 维度 | 评分 | 说明 |
|------|------|------|
| 目标一致性 | 9/10 | 代码实现与文档高度一致，架构边界严格执行 |
| 架构设计 | 9/10 | 分层清晰，依赖方向正确，声明式工具注册优雅 |
| 代码质量 | 8/10 | 命名规范，错误处理完善，安全多层防护 |
| 可维护性 | 8.5/10 | 新人友好，扩展方便，文档完善 |
| 测试覆盖 | 8/10 | 51 个测试文件，覆盖各层级，测试质量高 |

---

## 二、先前审查问题修复状态

上次审查（v1 报告）发现的 17 个问题中，**13 个已修复，2 个部分改进，2 个仍需关注**：

| # | 问题 | 状态 | 说明 |
|---|------|------|------|
| P0-1 | SessionStore 每次创建新连接 | ✅ **已修复** | `session.py:43-53` 现在维护持久连接 `self._conn`，`__del__` 关闭 |
| P0-2 | exec_command 命令注入 | ✅ **已修复** | 增加长度限制 `_MAX_COMMAND_LENGTH=4096`，新增 `$(`、反引号、`eval`、`exec`、`base64|sh` 正则 |
| P0-3 | webfetch 缺少 SSRF 防护 | ✅ **已修复** | `web.py:11-33` 实现 `_PRIVATE_NETWORKS` + `_is_private_ip()` 检查 |
| P1-4 | Config 浅层合并丢失嵌套 | ✅ **已修复** | `config.py:14-22` 实现 `_deep_merge()` 递归合并 |
| P1-5 | 文档数据不同步 | ⚠️ **仍需关注** | 详见下方新发现 |
| P1-6 | Web state.py 全局状态 | ✅ **已修复** | `ServerState` 类封装所有状态 (`state.py:39-52`) |
| P1-7 | SubAgentManager 内存泄漏 | ✅ **已修复** | `_cleanup_completed()` 自动清理，上限 `_max_completed=100` |
| P1-8 | _base.py 循环导入 | ✅ **已修复** | 使用 `from __future__ import annotations` + `TYPE_CHECKING` |
| P1-9 | patch diff 解析不健壮 | ✅ **已改进** | 增加 `\ No newline` 标记处理和 context 行验证 |
| P1-10 | SessionStore 未启用 CASCADE | ✅ **已修复** | `_connect()` 设置 `PRAGMA foreign_keys = ON`，`delete_session` 依赖 CASCADE |
| P2-11 | API key 明文持久化 | ✅ **已修复** | `save()` 排除敏感字段，设置 `0o600` 文件权限 |
| P2-12 | grep 性能限制 | ⚠️ **部分改进** | 增加 `_MAX_FILE_SIZE` 跳过大文件，但仍为纯 Python 实现 |
| P2-13 | 路由组织不一致 | ✅ **已修复** | 所有路由迁移到 `routes/` 目录使用 `APIRouter` |
| P2-14 | 重复 audit logging | ✅ **已修复** | `_audit_tool_call()` 辅助函数已在 `_base.py:94-111` |
| P2-15 | exec_command 硬编码超时 | ✅ **已修复** | 增加 `timeout` 参数，回退到 `config.security.command_timeout` |
| P2-16 | 缺少 Task 路由测试 | ✅ **已修复** | `web/tests/` 新增 `test_tasks.py` 和 `test_task_chat.py` |
| P2-17 | SDK events 收集器泄漏 | ⚠️ **仍需关注** | 详见下方新发现 |

---

## 三、做得好的地方

### 1. 架构设计精良（9/10）

**依赖方向严格执行**——通过代码扫描验证，`core/` 没有任何地方导入 `cli/`、`tui/`、`web/` 或 `sdk/`。这是整个项目最大的亮点：

```
SDK (cody/sdk/)  →  Core (cody/core/)  →  Tools (core/tools/)
CLI (cody/cli/)  →  SDK                →  Core
TUI (cody/tui/)  →  SDK                →  Core
Web Backend      →  Core (直接)
```

- CLI (`cli/main.py:13`) 正确使用 `from ..sdk.client import AsyncCodyClient`
- TUI 同样通过 SDK 访问 Core
- Web Backend 直接使用 Core（符合文档描述，因为 Web 需要更底层的控制）

### 2. 声明式工具注册系统

`tools/registry.py` 的设计极为优雅：

```python
CORE_TOOLS = FILE_TOOLS + SEARCH_TOOLS + COMMAND_TOOLS + ...
SUB_AGENT_TOOLSETS = {
    "code": FILE_TOOLS + SEARCH_TOOLS + COMMAND_TOOLS,
    "research": [read_file, list_directory, grep, glob, search_files],  # 只读
    "test": [read_file, write_file, edit_file, ...],  # 无子agent
}
```

- 新增工具只需 3 步：定义函数 → import → 加入列表
- 子 Agent 工具隔离通过集合交集自然实现
- `_with_model_retry` 装饰器将 `ToolError` 转为 `ModelRetry`，让 AI 自纠错

### 3. 多层安全防护体系

| 层级 | 机制 | 位置 |
|------|------|------|
| 路径安全 | `_resolve_and_check()` 强制 workdir/allowed_roots 边界 | `_base.py:27-63` |
| 命令安全 | 正则黑名单 + 用户白/黑名单 + 长度限制 | `command.py:14-68` |
| 网络安全 | SSRF 防护（私有 IP 检查） | `web.py:11-57` |
| 权限系统 | ALLOW/CONFIRM/DENY 三级权限 | `permissions.py:15-46` |
| 认证 | Bearer token + WebSocket auth | `middleware.py` |
| 限流 | 令牌桶算法 | `rate_limiter.py` |
| 审计 | 每个写操作自动记录 | `_base.py:94-111` |
| 配置安全 | 敏感字段排除持久化 + 0o600 权限 | `config.py:226-246` |

### 4. SDK Builder 模式

```python
client = (
    Cody()
    .workdir("/project")
    .model("claude-sonnet-4-0")
    .base_url("https://api.example.com/v1")
    .thinking(enabled=True, budget=10000)
    .on("tool_call", my_handler)
    .build()
)
```

流畅的链式 API，降低了接入门槛。三种构建方式（Builder / 直接参数 / Config 对象）覆盖不同使用场景。

### 5. 错误处理体系完善

- **Core 层**: `ToolError` 基类 + 3 个语义子类（`ToolInvalidParams` / `ToolPathDenied` / `ToolPermissionDenied`），每个携带 `ErrorCode` 枚举
- **SDK 层**: 10 种细粒度错误类型
- **Web 层**: `CodyAPIError` 统一映射为结构化 JSON 响应
- **自愈机制**: `_with_model_retry` 让 AI 从工具错误中恢复

### 6. 上下文管理和流式处理

- **自动上下文压缩**: `compact_messages()` 在接近 token 限制时自动压缩历史（`context.py:46-89`）
- **结构化流事件**: `StreamEvent` 联合类型（6 种事件），支持 thinking/text_delta/tool_call/tool_result/compact/done
- **CJK token 估算**: 中文字符按 1.5 token 计算（`context.py:22-31`）

---

## 四、当前仍存在的问题

### 严重问题 (P0)

#### 1. CLI 子命令直接导入 Core，违反架构分层

**位置**:
- `cody/cli/commands/sessions.py:7` — `from ...core import SessionStore`
- `cody/cli/commands/skills.py:9-10` — `from ...core import Config` + `from ...core.skill_manager import SkillManager`
- `cody/cli/commands/config.py:7` — `from ...core import Config`
- `cody/cli/commands/init_cmd.py:8-9` — 直接导入 Core
- `cody/cli/main.py:11-12` — `from ..core import Config` + `from ..core.log import setup_logging`

CLAUDE.md 明确规定 **"CLI/TUI 通过 SDK（`AsyncCodyClient`）访问 core，不再直接导入 `AgentRunner`/`SessionStore`"**。但 CLI 子命令直接实例化 `SessionStore()` 和 `SkillManager()`，完全绕过了 SDK 层。

```python
# sessions.py - 当前（违规）
store = SessionStore()  # 直接使用 Core

# 应该是
client = AsyncCodyClient(workdir=".")
sessions = await client.list_sessions(limit=limit)
```

`main.py` 中的 `Config.load()` 和 `setup_logging()` 可以辩解为"启动必需"，但 `sessions.py`、`skills.py` 完全可以通过 SDK 方法完成，且 SDK 已提供对应方法（`list_sessions()`, `list_skills()`, `get_skill()` 等）。

**影响**: 如果 SDK 层添加了缓存、事件通知、指标收集等增强功能，CLI 子命令将无法受益。更重要的是，这违反了文档中声明的架构原则。

**建议**: 将 `sessions.py` 和 `skills.py` 重构为使用 `AsyncCodyClient`，保持 `main.py` 中的 `Config.load()` 作为唯一允许的直接 Core 导入（用于引导 SDK 客户端创建）。

#### 2. `_stream_run()` 返回类型不明确

**位置**: `cody/sdk/client.py:449-476`

```python
async def _stream_run(self, prompt, session_id=None):
    """Internal streaming run (called when run(stream=True))."""
    async for chunk in self.stream(prompt, session_id=session_id):
        ...
        yield chunk
```

`_stream_run()` 是一个 async generator，但在 `run()` 方法中（`client.py:364`）它被 `return self._stream_run(...)` 返回。这意味着 `run(stream=True)` 返回的是一个未经类型注解的 async generator，而 `run()` 方法的返回类型声明中未体现这一点。调用者需要知道 `stream=True` 时返回的是 `AsyncIterator` 而非 `RunResult`。

**建议**: 添加返回类型重载声明（`@overload`），或将 `run(stream=True)` 重定向到 `stream()` 方法以保持 API 清晰。

#### 2. `CodyClient` 同步包装器中的事件循环冲突

**位置**: `cody/sdk/client.py:825-833`

```python
def _run_async(coro):
    try:
        asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)
```

当在已有事件循环的环境中（如 Jupyter Notebook、FastAPI 后台任务）调用 `CodyClient` 时，它会在新线程中运行 `asyncio.run()`。这个方案存在问题：
- 新线程中的 `asyncio.run()` 创建了一个全新的事件循环，与主循环不共享状态
- `SessionStore` 的 SQLite 连接使用 `check_same_thread=False`，但跨事件循环使用 runner 可能导致不可预期的竞态
- 如果传入的 coroutine 持有主事件循环的资源（如 WebSocket 连接），会导致死锁

**建议**:
- 文档中明确标注 `CodyClient` 适用场景（纯同步上下文）
- 考虑使用 `nest_asyncio` 或 `anyio` 来更安全地处理嵌套事件循环

---

### 建议改进 (P1)

#### 3. Web Backend `state.py` 的配置和 Runner 缓存线程安全

**位置**: `web/backend/state.py:95-158`

```python
def get_config(workdir: Path) -> Config:
    key = str(workdir)
    now = time.monotonic()
    if key in _state.config_cache:
        cached_config, cached_at = _state.config_cache[key]
        if now - cached_at < _CONFIG_CACHE_TTL:
            return cached_config.model_copy(deep=True)
    _state.config_cache[key] = (Config.load(workdir=workdir), now)
    return _state.config_cache[key][0].model_copy(deep=True)
```

`get_config()` 和 `get_runner()` 使用 dict 缓存但没有加锁。在 uvicorn 多 worker 或 asyncio 并发请求下：
- 两个请求可能同时触发缓存 miss，导致重复创建 Config/AgentRunner
- `_state.config_cache[key] = ...` 赋值本身在 CPython 中是原子的，但 check-then-act 模式不是

虽然 `model_copy(deep=True)` 防止了跨请求状态泄漏（设计良好），但重复创建 runner 是浪费的。

**建议**: 对 `config_cache` 和 `runner_cache` 的读写添加 `asyncio.Lock`，或使用 `cachetools.TTLCache` with thread-safe wrapper。

#### 4. `compact_messages()` 的摘要质量可改进

**位置**: `cody/core/context.py:66-89`

```python
def compact_messages(messages, max_tokens=100_000, keep_recent=4):
    # ...
    for msg in old_messages:
        brief = _summarize_message(content)  # 简单截断到 200 字符
        summary_parts.append(f"[{role}] {brief}")
```

当前的上下文压缩仅做简单截断（前 200 字符），不使用 LLM 进行语义摘要。对于工具调用密集的对话（大量 JSON 输出），截断后的摘要几乎没有信息量。

**建议**:
- 对工具调用结果做特殊处理（只保留工具名和成功/失败状态）
- 考虑使用小模型做语义摘要（可选功能，通过 config 开关控制）
- 至少过滤工具返回中的大段代码块

#### 5. 文档中的数据仍不同步

以下数据在不同文档中存在差异：

| 数据项 | 实际值 | 说明 |
|--------|--------|------|
| 测试数 | 约 686+ 函数（51 文件） | README.md 说 "673 total"，CONTRIBUTING.md 说 "652+"，CLAUDE.md 说 "588" core 测试 + "85" web 测试 + "33" 前端 |
| 工具数描述 | README "30+ AI tools"，CLAUDE.md "28 个工具函数" | 实际 registry.py 中 CORE_TOOLS + MCP_TOOLS = 28 个函数 |

**建议**: 确定一个权威数据源（如 registry.py 和 pytest count），在发版时自动更新文档中的数字。

#### 6. `grep` 工具仍为纯 Python 实现

**位置**: `cody/core/tools/search.py:23-91`

已增加 `_MAX_FILE_SIZE` 限制（1MB），但核心仍是逐文件逐行扫描。在有 10,000+ 文件的大型项目中，即使有 gitignore 过滤，性能也会是瓶颈。

**建议**:
- 检查 `rg`（ripgrep）是否可用，优先使用 subprocess 调用
- 或至少并发化文件读取（`asyncio.to_thread` + `asyncio.gather`）

#### 7. `list_sessions()` 返回的 Session 对象包含空 messages 列表

**位置**: `cody/core/session.py:183-203`

```python
def list_sessions(self, limit=20):
    # ...返回 Session(messages=[])
```

`list_sessions()` 为效率不查 messages，但返回的 `Session` 对象的 `messages` 字段是空列表 `[]`。这容易误导调用者认为会话没有消息。SDK 层 (`client.py:586-600`) 使用 `len(s.messages)` 作为 `message_count`，始终返回 0。

**建议**:
- `list_sessions()` 应使用 SQL `COUNT()` 子查询返回实际消息数
- 或在 `Session` 中添加 `message_count: int | None` 字段，`messages` 设为 `None` 表示未加载

#### 8. Web Backend 中 `get_auth_manager()` 和 `get_rate_limiter()` 异常被静默吞掉

**位置**: `web/backend/state.py:64-86`

```python
def get_auth_manager():
    try:
        config = Config.load(workdir=Path.cwd())
        _state.auth_manager = AuthManager(config=config.auth)
    except Exception:
        return None

def get_rate_limiter():
    try:
        ...
    except Exception:
        pass
```

配置加载失败时静默返回 `None`，不记录日志。这意味着认证和限流可能在部署中悄无声息地被禁用。

**建议**: 至少添加 `logger.warning()` 记录初始化失败原因。

---

### 可选改进 (P2)

#### 9. `CodyBuilder` 的 `mcp_server()` 和 `lsp_languages()` 类型不严谨

**位置**: `cody/sdk/client.py:131-139`

```python
def mcp_server(self, server: dict) -> "CodyBuilder":
    self._mcp_servers.append(server)
    return self

def lsp_languages(self, languages: list[str]) -> "CodyBuilder":
    self._lsp_languages = languages
    return self
```

`mcp_server()` 接受裸 `dict`，没有结构验证。用户传入缺少必要字段的 dict 会在后续运行时才报错。

**建议**: 使用 `TypedDict` 或 Pydantic model 约束 `server` 参数结构。

#### 10. `exec_command` 中 `$()` 被完全禁止可能过于严格

**位置**: `cody/core/tools/command.py:29`

```python
re.compile(r'\$\('),  # command substitution $(...)
```

这完全禁止了命令替换 `$()`，但很多合法命令使用这种语法（如 `cd $(git rev-parse --show-toplevel)`、`echo $(date)` 等）。同样 `eval` 和 `exec` 作为完整单词匹配可能误伤（如 `gradle` 命令中的 `exec` task）。

**建议**:
- 将 `$()` 限制改为仅检测明显危险组合（如 `$(curl ...)`、`$(wget ...)`）
- 或提供 config 选项允许用户放宽此限制
- `exec` 匹配改为更精确的 `\bexec\s+` 以减少误报

#### 11. 多处使用 `Optional[X]` 而非 `X | None`

**位置**: 全局（`runner.py`、`deps.py`、`session.py`、`sub_agent.py` 等）

CLAUDE.md 规定项目使用 Python 3.10+，应优先使用 `X | None` 联合类型语法。但代码中仍大量使用 `from typing import Optional` + `Optional[X]`。

**建议**: 这不影响功能，但为保持代码风格一致性，可逐步迁移到 `X | None` 语法（优先在新代码中使用）。

#### 12. `CodyResult.from_raw()` 中的 `part_kind` 字符串匹配

**位置**: `cody/core/runner.py:98-127`

```python
if part.part_kind == "thinking" and part.content:
    thinking_parts.append(part.content)
elif part.part_kind == "tool-call":
    ...
```

直接使用字符串字面量匹配 `part_kind`，如果 pydantic-ai 的消息类型名发生变化会静默失败。

**建议**: 使用 `isinstance()` 检查或导入 pydantic-ai 的具体 Part 类型进行匹配，而非依赖字符串。

#### 13. `shared.py` 中的中文硬编码

**位置**: `cody/shared.py:33-37`

```python
def compact_message(original, compacted, tokens_saved):
    return (
        f"⚡ 上下文已压缩：{original} → {compacted} 条消息，"
        f"节省约 ~{tokens_saved} tokens"
    )
```

UI 文本硬编码为中文，不利于国际化。

**建议**: 如果项目定位面向国际用户，考虑使用 i18n 框架或至少提供英文版。如果仅面向中文用户则无需改动。

#### 14. `_relevance_score()` 中的 `content.lower()` 全文小写化

**位置**: `cody/core/context.py:254-260`

```python
content_lower = content.lower()
for word in query_words:
    count = content_lower.count(word)
```

对每个文件的全部内容调用 `.lower()` 并多次 `.count()`，在大文件上性能不佳。

**建议**: 使用 `re.findall()` 配合 `re.IGNORECASE` 一次性完成，或预编译关键词正则。

---

## 五、架构验证

### 依赖方向验证

| 检查项 | 状态 | 依据 |
|--------|------|------|
| Core 不导入 CLI | ✅ 通过 | 扫描 `cody/core/` 全部 22 个 Python 文件，零违规 |
| Core 不导入 TUI | ✅ 通过 | 零违规 |
| Core 不导入 Web | ✅ 通过 | 零违规 |
| Core 不导入 SDK | ✅ 通过 | 零违规 |
| CLI 通过 SDK 访问 Core | ⚠️ 部分违规 | `main.py` 的 run/chat 正确使用 SDK，但 `commands/sessions.py` 和 `commands/skills.py` 直接导入 Core |
| TUI 通过 SDK 访问 Core | ✅ 通过 | `tui/app.py` → `AsyncCodyClient` |
| Web Backend 直接使用 Core | ✅ 符合文档 | `state.py` 导入 `cody.core.*` |
| client.py 为纯 re-export | ✅ 通过 | 仅 re-export SDK 公开符号 |

### 工具系统验证

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 工具注册声明式 | ✅ 通过 | `registry.py` 中 8 个工具列表 + 2 个注册函数 |
| 子 Agent 工具隔离 | ✅ 通过 | research 无写/执行权限，test 无子 Agent |
| `_with_model_retry` 包装 | ✅ 通过 | 所有工具通过 `register_tools()` 自动包装 |
| 权限检查一致性 | ✅ 通过 | 所有写操作调用 `_check_permission()` |
| 审计日志一致性 | ✅ 通过 | 写操作和命令执行统一调用 `_audit_tool_call()` |

### 安全措施验证

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 路径遍历防护 | ✅ 通过 | `_resolve_and_check()` + `is_relative_to()` |
| 命令注入防护 | ✅ 通过 | 15 条正则 + 长度限制 + 白/黑名单 |
| SSRF 防护 | ✅ 通过 | 7 个私有网段检查 + `allow_private_urls` 配置 |
| 敏感数据保护 | ✅ 通过 | `save()` 排除 API key/token + 0o600 权限 |
| 权限系统 | ✅ 通过 | 读操作 ALLOW，写操作 CONFIRM，28 个工具全覆盖 |

---

## 六、按模块分项评价

### Core Engine (9/10)

**亮点**:
- `runner.py` 作为中枢设计合理，职责清晰（Agent 创建 → 工具注册 → 依赖注入 → 执行）
- `CodyResult.from_raw()` 提取 thinking/tool_traces 的实现简洁
- `_build_allowed_roots()` 的安全路径合并设计严密
- 循环依赖通过延迟导入干净地解决（`sub_agent.py:303-309`）
- `CompactEvent` 让调用者感知上下文压缩（良好的 observability）

**可改进**:
- `_compact_history_if_needed()` 在 ModelMessage ↔ dict 之间转换不够优雅，可考虑让 `compact_messages()` 直接接受 ModelMessage
- 多处使用 `Optional` 而非 `X | None`

### SDK (8.5/10)

**亮点**:
- Builder 模式 + 直接构造 + Config 对象三种方式并存
- 事件系统和指标收集完整
- `AsyncCodyClient` 的延迟初始化（`_runner=None`, `_session_store=None`）避免不必要的开销
- `CodyClient` 同步包装器为简单使用场景降低门槛
- `set_config()` 公开 API 优于直接操作 `_core_config`

**可改进**:
- `run(stream=True)` 的返回类型不够明确
- `_run_async()` 的事件循环处理在 nested loop 场景下有风险
- `tool()` 方法每次创建新 Config/SkillManager/CodyDeps，不使用缓存

### CLI (7.5/10)

**亮点**:
- `run` 和 `chat` 命令通过 SDK (`AsyncCodyClient`) 访问 Core —— 正确
- CLI 参数设计完善（`--model`、`--thinking`、`--workdir`、`--allow-root`）
- `commands/` 子目录组织清晰
- `_render_stream` 封装了流式渲染逻辑

**需改进**:
- **架构违规**: `commands/sessions.py` 和 `commands/skills.py` 直接导入 Core（`SessionStore`、`SkillManager`），绕过 SDK 层（P0-1）
- `chat` 命令中的 `asyncio.get_event_loop()` 在 Python 3.12+ 已弃用

### TUI (8/10)

**亮点**:
- 使用 Textual 框架，代码整洁
- 正确通过 SDK 层访问 Core

### Web Backend (8/10)

**亮点**:
- FastAPI 使用规范（Depends 注入、Router 分组、中间件分层）
- `ServerState` 类封装可变状态
- Config 缓存使用 `model_copy(deep=True)` 防止状态泄漏
- Runner 缓存使用 config fingerprint 检测配置变更
- 中间件按正确顺序注册（auth → rate_limit → audit）

**可改进**:
- 缓存操作非线程安全（P1-3）
- 异常静默吞掉（P1-8）
- `get_sub_agent_manager()` 使用 `asyncio.Lock` 但 config/runner 缓存未加锁

### Web Frontend (8/10)

**亮点**:
- TypeScript 类型定义完整 (`types/index.ts`)
- 组件分层清晰（pages/ + components/ + hooks/ + api/）
- API client 封装良好

### 测试 (8/10)

**亮点**:
- 51 个测试文件覆盖全部层级
- `conftest.py` 提供良好的 fixture 基础设施（`isolated_store`、`MockContext`）
- 文件操作测试正确使用 `tmp_path`
- Web 测试使用 FastAPI `TestClient` 和 `httpx.AsyncClient`

**可改进**:
- `list_sessions()` 返回 `message_count=0` 的问题应有对应测试覆盖
- 可增加更多边界条件测试（超大文件、Unicode 路径、并发操作等）

---

## 七、总结

Cody v1.7.4 是一个**工程成熟度很高的 AI Agent 框架**。与上次审查相比，13/17 个已知问题已修复，代码安全性和健壮性显著提升。

**当前最值得关注的 3 个改进方向**：

1. **CLI 架构违规修复** (P0-1): CLI 子命令（sessions/skills）直接导入 Core 而非通过 SDK，违反文档声明的分层架构
2. **SDK 类型安全** (P0-2/P0-3): `run(stream=True)` 返回类型不明确，`_run_async()` 事件循环处理需更安全
3. **Web Backend 并发安全** (P1-3): 配置和 Runner 缓存需加锁保护

**项目成熟度**: **Production-Ready**。架构边界严格执行，安全防护多层覆盖，适合作为构建 AI Coding Agent 的框架基础。

---

*审查方法：通读全部源码文件（22 core + 7 SDK + 9 CLI + 3 TUI + 22 web backend + 15 tools = 78 个 Python 文件），交叉验证文档与实现，检查依赖方向和安全措施。*
