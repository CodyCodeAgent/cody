# Cody 开发规范

> Open-source AI Coding Agent Framework

## 核心原则

1. **框架核心为先** — Core 是框架的核心引擎，CLI、TUI、SDK 和 Web Backend 都是接入层。所有功能先在 core/ 实现，再由各层暴露给用户。
2. **测试必须有** — 没有测试的代码不合并。不只是"能跑"，要验证行为正确。
3. **准确度 > 性能** — 工具的结果准确性是底线。宁可慢一点也不能出错。
4. **简单直接** — 不过度设计，不提前抽象。三行重复代码好过一个过早的抽象。

---

## 架构规范

### 代码分层

```
cody/
├── core/           # 框架核心引擎（不依赖任何接入层）
│   ├── config.py       # 配置管理
│   ├── runner.py       # Agent 执行引擎 + CodyDeps
│   ├── tools.py        # 内置工具（文件、搜索、命令、todo、question）
│   ├── session.py      # 会话管理（SQLite）
│   ├── skill_manager.py # Skill 加载与管理
│   ├── sub_agent.py    # 子 Agent 编排
│   ├── mcp_client.py   # MCP 协议客户端
│   ├── lsp_client.py   # LSP 语言服务客户端
│   ├── context.py      # 上下文管理（compact, chunk, select）
│   ├── web.py          # Web 搜索 + 抓取
│   ├── errors.py       # 结构化错误（ErrorCode, CodyAPIError）
│   ├── audit.py        # 审计日志（SQLite）
│   ├── auth.py         # 认证管理（HMAC-SHA256 token）
│   ├── permissions.py  # 工具级权限（allow/deny/confirm）
│   ├── file_history.py # 文件 undo/redo 快照
│   └── rate_limiter.py # 滑动窗口限流
├── sdk/            # Python SDK（一等公民模块，直接包装 core）
│   ├── client.py       # CodyClient (同步) + AsyncCodyClient (异步)
│   ├── types.py        # SDK 响应类型 — RunResult, Usage, StreamChunk 等
│   ├── errors.py       # SDK 错误层级 — 10 种细粒度错误类型
│   └── config.py       # SDK 配置 — SDKConfig, ModelConfig, config() 工厂
├── skills/         # 内置 Skills（git, github, docker, npm, python, rust, go, java, web, cicd, testing）
├── client.py       # 向后兼容 shim — re-export sdk/ 的公开符号
├── tui/            # TUI 界面（Textual），调用 core
│   ├── __init__.py    # 重导出 run_tui, CodyTUI, MessageBubble, StreamBubble
│   ├── app.py         # CodyTUI 主应用 + run_tui() 入口
│   └── widgets.py     # MessageBubble, StreamBubble, StatusLine
└── cli/            # CLI 界面（Click），调用 core
    ├── __init__.py    # 重导出 main, _handle_command, _build_history_from_session
    ├── main.py        # Click group + run/chat/tui 核心命令
    ├── commands/      # 子命令模块（init, sessions, skills, config）
    ├── rendering.py   # 流式渲染 + spinner
    └── utils.py       # 辅助函数 + console 单例

web/backend/        # 统一 Web Backend（FastAPI:8000），直接导入 core
```

**关键约束：**
- `core/` 内的代码 **不允许** 导入 `cli/`、`tui/`、`sdk/` 或 `web/`
- 所有接入层都通过 `core/` 提供的接口工作
- `cody/sdk/` 是一等公民模块，直接包装 core，提供 Builder 模式、事件流、指标等高级 API
- `cody/client.py` 是向后兼容 shim，仅 re-export `sdk/` 的公开符号，新代码应直接使用 `cody.sdk`
- 新功能应该加在 `core/`，然后在各接入层暴露

### 依赖方向

```
cli/ ────→
tui/ ────→  core/*
sdk/   ──→  core/*（in-process，无 HTTP）
web/backend/ ──→ core/*（直接 import）
```

禁止反向依赖。禁止 `core/` 依赖任何 CLI（click, rich）、TUI（textual）或 Web（fastapi）的库。

---

## 测试规范

### 必须测试

| 变更类型 | 测试要求 |
|----------|----------|
| 新工具（tools.py） | 至少 3 个测试：正常路径、边界情况、错误处理 |
| 新 API 端点（web/backend/） | 至少 2 个测试：正常响应、错误响应 |
| 新 CLI 命令（cli/） | 至少 1 个测试：基本调用 |
| Bug 修复 | 必须附带回归测试（先写测试复现 bug，再修） |
| 核心逻辑变更 | 覆盖所有受影响路径 |

### 测试工具

```bash
# 运行全部测试
python3 -m pytest tests/ -v

# 运行单个文件
python3 -m pytest tests/test_tools.py -v

# 运行匹配名称的测试
python3 -m pytest tests/ -k "grep" -v
```

### 测试原则

1. **不依赖真实 API Key** — 用 `MockContext` / Pydantic AI `TestModel` 模拟 LLM
2. **用 `tmp_path`** — 所有文件操作在临时目录，不污染真实文件系统
3. **测 行为 不测 实现** — 断言输出结果，不断言内部调用
4. **异步测试** — 工具函数用 `@pytest.mark.asyncio` + `async def test_xxx`
5. **测试命名** — `test_<功能>_<场景>`，例如 `test_grep_skips_binary_files`

### MockContext 用法

```python
from cody.core.tools import grep
from cody.core.config import Config
from cody.core.skill_manager import SkillManager
from cody.core.runner import CodyDeps

class MockContext:
    def __init__(self, workdir):
        config = Config()
        self.deps = CodyDeps(
            config=config,
            workdir=Path(workdir),
            skill_manager=SkillManager(config),
        )

@pytest.mark.asyncio
async def test_grep_basic(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "hello.py").write_text("def hello(): pass\n")
    result = await grep(ctx, "def hello")
    assert "hello.py:1:" in result
```

### Web Backend 测试用法

```python
from fastapi.testclient import TestClient
from web.backend.app import app

def test_health():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
```

---

## 代码风格

### Lint 和格式化

```bash
# 检查
python3 -m ruff check cody/ tests/

# 自动修复
python3 -m ruff check cody/ tests/ --fix

# 格式化（可选，以 ruff 为准）
python3 -m black cody/ tests/
```

### 规则

- **行宽** — 100 字符
- **Python 版本** — 3.10+（支持 `X | None` 联合类型，不用 `match/case`）
- **类型注解** — 公开函数必须有类型注解，内部函数尽量有
- **导入顺序** — stdlib → 三方库 → 项目内部（ruff 自动管理）
- **文档字符串** — 公开 API（工具函数、Server 端点）必须有 docstring，内部辅助函数按需

### 命名约定

- 文件名：`snake_case.py`
- 类名：`PascalCase`
- 函数/变量：`snake_case`
- 常量：`UPPER_SNAKE_CASE`
- 内部函数：`_leading_underscore`

---

## Git 规范

### 分支

- `main` — 稳定分支，所有测试必须通过
- `feature/xxx` — 功能分支，从 main 拉取
- `fix/xxx` — 修复分支

### 提交信息

格式：`<动词> <做了什么>`

```
Add grep tool with regex search and include filter
Fix path traversal security check using resolve()
Update FEATURES.md with engine-first roadmap
```

- 用英文
- 首字母大写
- 不加句号
- 动词用原形：Add / Fix / Update / Remove / Refactor

### 提交前检查

```bash
# 必须全部通过才能提交
python3 -m ruff check cody/ tests/
python3 -m pytest tests/ -v
```

---

## 新功能开发流程

1. **先写测试** — 或至少同时写测试。不接受"先实现后面再补测试"
2. **先在 core/ 实现** — 功能逻辑放在 `core/`
3. **SDK 暴露** — 在 `cody/sdk/` 包装 core 接口，提供 SDK 级别的 API（如果需要）
4. **Web Backend 端点** — 在 `web/backend/routes/` 暴露 API（如果需要）
5. **CLI 命令** — 在 `cli/` 提供界面（如果需要）
6. **更新文档** — 同步更新所有相关的 `.md` 文档（见下方"文档更新规范"）
7. **运行测试** — 全部通过
8. **运行 lint** — 零告警

### 示例：添加新工具

```
1. 在 core/tools/ 对应子模块实现工具函数（如 file_ops.py、search.py）
2. 把函数追加到 registry.py 对应的 *_TOOLS 列表（如 FILE_TOOLS、SEARCH_TOOLS）
3. 如果子 Agent 也要用，加到 SUB_AGENT_TOOLSETS 对应的 type 列表
4. 在 tests/test_tools.py 写 3+ 个测试
5. 更新 docs/CLI.md 和 docs/API.md 的工具列表
6. pytest + ruff 通过
```

> 不需要改 runner.py — `register_tools()` 会自动注册列表里的所有工具。

---

## 文档更新规范

**开发完新功能后，必须同步更新项目中的所有相关 `.md` 文档**，保持文档与代码同步。

### 需要检查的文档目录

| 目录 | 说明 |
|------|------|
| `./` | 根目录文档（README.md、CHANGELOG.md、CONTRIBUTING.md、CLAUDE.md 等） |
| `docs/` | 所有项目文档（CLI.md、API.md、ARCHITECTURE.md、FEATURES.md 等） |

### 提交前检查清单

确认所有相关的 `.md` 文档已更新：

- [ ] 根目录文档 — README.md、CHANGELOG.md、CONTRIBUTING.md、CLAUDE.md 等
- [ ] docs/ 目录文档 — CLI.md、API.md、ARCHITECTURE.md、FEATURES.md 等

> **原则**：文档是代码的一部分，不是事后补充。代码合并前，文档必须先更新。
>
> **提示**：使用 `find . -name "*.md"` 列出所有 Markdown 文档，逐一检查是否需要更新。

---

## 当前状态

| 模块 | 测试数 | 状态 |
|------|--------|------|
| core/tools/ | 51 | 完善 |
| core/skill_manager.py | 40 | 完善 |
| core/lsp_client.py | 34 | 完善 |
| core/config.py | 33 | 完善 |
| core/runner.py | 24 | 完善 |
| core/auth.py | 23 | 完善 |
| core/web.py | 22 | 完善 |
| client.py | 22 | 完善 |
| sdk/ | 65 | 完善 |
| core/sub_agent.py | 21 | 完善 |
| web/backend (WS) | 21 | 完善 |
| web/backend (projects) | 20 | 完善 |
| core/audit.py | 19 | 完善 |
| core/permissions.py | 18 | 完善 |
| core/context.py | 16 | 完善 |
| cli/ | 25 | 完善 |
| core/rate_limiter.py | 16 | 完善 |
| core/file_history.py | 15 | 完善 |
| core/session.py | 14 | 完善 |
| core/mcp_client.py | 14 | 完善 |
| tui/ | 17 | 完善 |
| core/errors.py | 11 | 完善 |
| web/backend (middleware) | 9 | 完善 |

**总计：652+ 个测试（576 core/sdk + 76 web），ruff 零告警**

**当前版本：v1.7.4（见 CHANGELOG.md）**

---

## 已知架构注意事项

1. **循环依赖** — `sub_agent.py` 的 `_execute()` 用延迟导入打破 `runner → sub_agent → runner` 循环，不要移到模块顶部
2. **状态缓存策略** — `web/backend/state.py` 管理：Config 按 workdir 缓存（60s TTL，deep copy 后返回），SessionStore 全局单例，SkillManager 每次请求新建（保证读到最新 skill 文件）

---

## 快速上手路径

如果你刚接手项目，建议按这个顺序：

1. **跑通测试** — `pip install -e ".[dev]" && python3 -m pytest tests/ -v`
2. **看 `core/runner.py`** — 理解框架核心引擎（模块 docstring 有架构概览）
3. **看 `core/tools/`** — 理解工具注册模式（`registry.py` 中的 `*_TOOLS` 列表）
4. **看 `cody/sdk/client.py`** — 理解 SDK 如何包装 core（Builder 模式、事件流、指标）
5. **看 `web/backend/app.py`** — 理解 Web Backend 如何调用 core
6. **看本文件** — 了解代码规范
7. **看 `docs/API.md`** — 了解对外 API

有问题看测试——每个模块都有对应的测试文件，是最好的"活文档"。
