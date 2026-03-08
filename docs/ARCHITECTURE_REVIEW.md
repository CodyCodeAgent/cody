# Cody 架构评审报告

> 评审日期：2026-03-07
> 代码版本：v1.7.3
> 项目规模：111 Python 文件，~20,000 行 Python + React 前端

---

## 一、总体评价

**Cody 的架构设计水平在同类开源项目中属于上游水平。** 核心设计决策（框架 vs 应用、依赖方向、声明式工具注册、DI 容器）都是正确的。代码组织清晰、模块边界合理、层次分明。以下从架构师视角给出优点、风险点和改进建议。

### 评分卡

| 维度 | 评分 | 说明 |
|------|------|------|
| 模块化 | ★★★★☆ | core/sdk/cli/tui/web 分层清晰，core 不反向依赖 |
| 可扩展性 | ★★★★★ | 声明式工具注册 + Skills 标准 + MCP + Sub-Agent，扩展路径丰富 |
| 可测试性 | ★★★★☆ | DI 容器设计好，570+ 核心测试覆盖面广 |
| 代码质量 | ★★★★☆ | 命名规范、注释到位、错误层级清晰 |
| 安全性 | ★★★★☆ | 多层安全栈（路径沙箱 + 权限 + 审计 + 限流） |
| 可维护性 | ★★★☆☆ | tools.py 1237 行需拆分；部分单例管理可改进 |
| 性能设计 | ★★★☆☆ | 缓存 TTL 策略合理，但缺少连接池和批量操作优化 |

---

## 二、架构亮点（值得保持）

### 1. 框架定位精准

```
Core Engine (框架) → SDK/CLI/TUI/Web (参考实现)
```

这是最关键的架构决策。core 不依赖任何 UI 框架，任何人可以基于 core 构建新的集成（IDE 插件、CI bot、Slack app）。**这比很多同类项目（monolithic CLI）的设计领先一个层级。**

### 2. 依赖方向严格单向

```
cli/ ──→ core/    ✓ 正确
tui/ ──→ core/    ✓ 正确
web/ ──→ core/    ✓ 正确
sdk/ ──→ core/    ✓ 正确
core/ ──→ cli/    ✗ 不存在（已验证）
```

这条规则在代码中得到严格遵守。这是架构健康度的基石。

### 3. 声明式工具注册

```python
# tools.py 底部
CORE_TOOLS = FILE_TOOLS + SEARCH_TOOLS + COMMAND_TOOLS + ...
SUB_AGENT_TOOLSETS = {
    "code": FILE_TOOLS + SEARCH_TOOLS + COMMAND_TOOLS,
    "research": [read_file, list_directory, grep, glob, search_files],  # 只读
    ...
}
```

工具注册不是散落在各处的 `agent.tool()` 调用，而是集中在一个声明式列表中。添加新工具只需两步：写函数 + 加入列表。**这种设计让工具管理的认知负担极低。**

### 4. CodyDeps 依赖注入容器

```python
@dataclass
class CodyDeps:
    config: Config
    workdir: Path
    skill_manager: SkillManager
    mcp_client: Optional[MCPClient] = None
    sub_agent_manager: Optional[SubAgentManager] = None
    # ... 全部可选
```

仅 37 行代码，干净利落地解决了工具函数的依赖注入问题。必选字段只有 3 个，其余全部可选，支持最小化构造（测试时友好）。

### 5. 错误类型层级设计

```
ToolError (base)
├── ToolPermissionDenied → 403
├── ToolPathDenied       → 403
└── ToolInvalidParams    → 400
```

按类型映射 HTTP 状态码，不用字符串匹配。加上 `_with_model_retry` 包装器将 ToolError 转为 ModelRetry，让 LLM 可以自我纠正。**这种 "错误即信号" 的设计比简单抛异常高明得多。**

### 6. 渐进式 Skills 加载

启动时只解析 YAML frontmatter（~50-100 tokens/skill），完整指令按需加载。对于有数十个 Skills 的场景，这避免了启动时的 token 浪费。

---

## 三、架构风险点（需要关注）

### 风险 1：tools.py 是 God File（1237 行）

**严重程度：中高**

28 个工具函数 + 辅助函数 + 注册逻辑全部集中在一个文件中。随着工具数量增长（MCP 趋势下可能翻倍），这个文件会变成维护噩梦。

**问题表现：**
- 修改任何一个工具都要在 1200+ 行文件中定位
- git blame 和 merge conflict 频率会随文件大小线性增长
- 新贡献者打开这个文件会立刻失去方向感

**建议：拆分为工具子包**

```
core/tools/
├── __init__.py          # register_tools(), register_sub_agent_tools(), CORE_TOOLS
├── _base.py             # _check_permission, _resolve_and_check, _with_model_retry
├── file_tools.py        # read_file, write_file, edit_file, list_directory
├── search_tools.py      # grep, glob, patch, search_files
├── command_tools.py     # exec_command
├── skill_tools.py       # list_skills, read_skill
├── sub_agent_tools.py   # spawn_agent, get_agent_status, kill_agent
├── web_tools.py         # webfetch, websearch
├── lsp_tools.py         # lsp_diagnostics, lsp_definition, ...
├── history_tools.py     # undo_file, redo_file, list_file_changes
├── todo_tools.py        # todo_write, todo_read
└── user_tools.py        # question
```

`__init__.py` 保持声明式注册列表，每个子模块负责一类工具。**向后兼容：`from core.tools import register_tools` 不变。**

### 风险 2：AgentRunner 构造函数过重（13+ 依赖）

**严重程度：中**

```python
class AgentRunner:
    def __init__(self, config, workdir, ...):
        self.config = config
        self.workdir = workdir
        self.skill_manager = SkillManager(config, workdir)
        self.mcp_client = MCPClient(...)
        self.sub_agent_manager = SubAgentManager(...)
        self.lsp_client = LSPClient(...)
        self.audit_logger = AuditLogger(...)
        self.permission_manager = PermissionManager(...)
        self.file_history = FileHistory(...)
        self.todo_list = []
        # ... 还有 session_store 等
```

AgentRunner 同时负责：创建 Agent、注册工具、组装依赖、管理生命周期、执行 run/stream、会话管理、历史压缩。这违反了 SRP（单一职责原则）。

**建议：提取工厂 + 生命周期管理器**

```python
# core/factory.py
class CodyFactory:
    """构建 CodyDeps 的工厂，AgentRunner 只负责执行。"""
    @staticmethod
    def create_deps(config, workdir, **overrides) -> CodyDeps: ...

# AgentRunner 只接受 CodyDeps
class AgentRunner:
    def __init__(self, deps: CodyDeps): ...
```

这样 Runner 专注执行，构造逻辑外移。Web 的 `state.py` 已经有 `create_full_deps()` 做类似的事，可以统一。

### 风险 3：循环依赖用延迟导入解决（技术债务）

**严重程度：中**

```python
# sub_agent.py._execute()
async def _execute(self, agent_id, task, agent_type):
    from .tools import register_sub_agent_tools  # 延迟导入！
    from .deps import CodyDeps
```

延迟导入能工作，但它是一种 "隐式依赖"，IDE 无法静态分析，重构时容易遗漏。

**根因：** `runner.py` → `sub_agent.py` → `tools.py` → （间接）→ `runner.py` 形成环。

**建议：通过接口隔离打破循环**

```python
# core/protocols.py
class ToolRegistrar(Protocol):
    def register(self, agent, agent_type: str) -> None: ...

# sub_agent.py 只依赖 Protocol，不导入 tools
class SubAgentManager:
    def __init__(self, ..., tool_registrar: ToolRegistrar): ...
```

### 风险 4：web/backend/state.py 全局单例模式

**严重程度：中**

```python
_audit_logger: AuditLogger = None
_session_store: SessionStore = None
_config_cache: dict[str, tuple[Config, float]] = {}
_runner_cache: dict[str, tuple[AgentRunner, float]] = {}
```

模块级全局变量 + 手动 TTL 缓存。问题：

1. **测试隔离差** — 虽然有 `reset_state()`，但忘记调用就会污染
2. **内存泄漏风险** — `_runner_cache` 按 workdir 无限增长，没有 LRU 淘汰
3. **线程安全** — `_config_cache` 的 dict 操作在并发请求下可能竞争

**建议：**
- 使用 `functools.lru_cache` 或 `cachetools.TTLCache` 替代手动缓存
- 考虑 FastAPI 的 `Depends()` + `lifespan` 管理生命周期
- `_runner_cache` 加 maxsize 限制

### 风险 5：Config.load() 配置合并逻辑脆弱

**严重程度：低中**

```python
# config.py line 105-113
merged: dict = {}
if global_config.exists():
    merged.update(json.loads(global_config.read_text()))
if project_config.exists():
    merged.update(json.loads(project_config.read_text()))
```

`dict.update()` 是浅合并。如果全局配置有 `security: {allowed_commands: [...]}` 而项目配置有 `security: {blocked_commands: [...]}}`，项目配置会**完全覆盖** security 对象，丢失 `allowed_commands`。

**建议：使用深度合并**

```python
def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
```

### 风险 6：SDK tool() 方法每次调用创建新配置

**严重程度：低**

```python
# sdk/client.py - tool() 方法
async def tool(self, tool_name, params, workdir=None):
    config = Config.load(workdir=effective_workdir)  # 每次重新加载
    sm = SkillManager(config, effective_workdir)       # 每次新建
```

频繁的 `tool()` 调用会反复读取文件系统和解析配置。对于批量工具调用场景（如批量 grep）这是浪费。

**建议：** 在 `AsyncCodyClient` 中缓存 config 和 skill_manager，与 runner 使用相同的懒加载策略。

---

## 四、设计模式分析

### 使用得当的模式

| 模式 | 位置 | 效果 |
|------|------|------|
| **依赖注入** | CodyDeps → tools | 工具函数无全局状态，测试友好 |
| **Builder 模式** | CodyBuilder → AsyncCodyClient | SDK 构造灵活，链式调用清晰 |
| **声明式注册** | tools.py 底部列表 | 添加工具零摩擦 |
| **策略模式** | SUB_AGENT_TOOLSETS | 不同 Agent 类型不同工具集 |
| **渐进式加载** | SkillManager | 按需加载降低启动开销 |
| **事件驱动** | StreamEvent 体系 | Core 产生事件，消费者自行渲染 |
| **装饰器模式** | _with_model_retry | 横切关注点（错误转换）不侵入业务逻辑 |

### 缺失或可改进的模式

| 建议模式 | 位置 | 理由 |
|----------|------|------|
| **Protocol/Interface** | sub_agent ↔ tools | 打破循环依赖 |
| **工厂方法** | AgentRunner 构造 | 分离构建和执行职责 |
| **Repository 模式** | SessionStore | 当前直接操作 SQLite，加一层抽象利于切换存储后端 |
| **中间件链** | 工具执行 | 权限检查、审计、限流可抽象为工具中间件管道 |

---

## 五、模块尺寸分析

### Core 模块（5619 行）

```
tools.py          1236 行  ████████████████████████ 22.0%  ← 过大，建议拆分
runner.py          644 行  ████████████ 11.5%
lsp_client.py      496 行  █████████ 8.8%
mcp_client.py      333 行  ██████ 5.9%
skill_manager.py   319 行  ██████ 5.7%
sub_agent.py       285 行  █████ 5.1%
context.py         265 行  █████ 4.7%
web.py             245 行  ████ 4.4%
session.py         229 行  ████ 4.1%
project_instr.py   211 行  ████ 3.8%
config.py          200 行  ████ 3.6%
其余               1156 行  ████ 20.5%（8 个文件，平均 145 行）
```

**健康指标：** 除 tools.py 外，模块大小分布合理（100-500 行区间）。

### 测试覆盖

```
tests/             570+ 测试（核心 + SDK）
web/tests/          54 测试（Web 后端）
web/__tests__/      33 测试（前端）
总计               657+ 测试
```

测试/代码比约 1:3，对框架项目来说合理。

---

## 六、安全架构评估

### 做得好的

1. **路径沙箱** — `_resolve_and_check()` 先 resolve 再检查是否在 workdir/allowed_roots 内，防止 symlink 逃逸
2. **危险命令检测** — exec_command 检查 `rm -rf`、`dd`、fork bomb 等
3. **多层权限** — PermissionManager 支持 per-tool allow/deny/confirm
4. **审计日志** — SQLite 记录所有 tool_call、file_write、command_exec
5. **Sub-Agent 权限隔离** — research 类型只能读不能写

### 需要加强的

1. **Config 中存储 API Key** — `config.json` 明文存储 `model_api_key`，应考虑系统 keyring 或至少文件权限 0600
2. **exec_command 的命令注入** — 如果 LLM 构造恶意命令参数（如 `; rm -rf /`），需要确保使用列表形式 `subprocess.run([...])` 而非 `shell=True`
3. **webfetch SSRF** — 应限制 `webfetch` 不能访问内网地址（127.0.0.1, 10.x, 172.16.x 等）

---

## 七、横向对比

与同类项目对比（Claude Code CLI、Aider、OpenHands、SWE-Agent）：

| 特性 | Cody | Claude Code | Aider | OpenHands |
|------|------|-------------|-------|-----------|
| 框架 vs 工具 | ✅ 框架 | ✗ 工具 | ✗ 工具 | ✅ 框架 |
| SDK | ✅ 完整 | ✗ 无 | ✗ 无 | ✅ 有 |
| 多 UI 支持 | ✅ CLI+TUI+Web | CLI 只 | CLI 只 | Web 只 |
| Skills 标准 | ✅ agentskills.io | ✅ CLAUDE.md | ✗ | ✗ |
| MCP 集成 | ✅ | ✅ | ✗ | ✗ |
| Sub-Agent | ✅ 4 类型 | ✅ | ✗ | ✅ |
| LSP 集成 | ✅ 3 语言 | ✗ | ✗ | ✗ |

**Cody 在功能完整度上已经达到同类项目的前列。** 架构上"框架优先"的定位使其扩展性优于大部分竞品。

---

## 八、优先改进建议（按 ROI 排序）

| 优先级 | 改进项 | 投入 | 收益 |
|--------|--------|------|------|
| **P0** | 拆分 tools.py 为子包 | 中 | 可维护性大幅提升，降低新贡献者门槛 |
| **P1** | Config 深度合并 | 小 | 修复潜在的配置覆盖 bug |
| **P1** | state.py 缓存加 maxsize | 小 | 防止内存泄漏 |
| **P2** | 提取 AgentRunner 工厂 | 中 | 降低 Runner 复杂度，统一 deps 构建 |
| **P2** | Protocol 消除循环依赖 | 小 | 消除技术债务，改善 IDE 支持 |
| **P3** | API Key 安全存储 | 中 | 安全合规 |
| **P3** | 工具执行中间件管道 | 大 | 权限/审计/限流可插拔 |

---

## 九、总结

**Cody 是一个架构设计扎实的项目。** 核心的"框架 + 参考实现"模式、严格的依赖方向、声明式工具注册和 DI 容器设计，都体现了成熟的架构思维。代码规模控制得当（core 5600 行承载 28 个工具 + 完整基础设施），没有过度工程化。

最需要投入的是 **tools.py 拆分**（当前是全项目最大的文件，占 core 22%），其次是补齐几个低成本的防御性修复（Config 深度合并、缓存 maxsize）。安全栈已经比大多数同类项目完善，但 API Key 明文存储和 SSRF 防护值得关注。

整体来说：**这是一个可以放心投入长期维护的代码库。**
