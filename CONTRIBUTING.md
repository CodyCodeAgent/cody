# Cody 开发规范

## 核心原则

1. **Core 做厚，壳子做薄** — CLI 和 Server 都只是 core 引擎的接入层。所有功能先在 core/ 实现，然后 Server 和 CLI 都能用。Server/SDK 是差异化交付方式，CLI 保证可用。
2. **测试必须有** — 没有测试的代码不合并。不只是"能跑"，要验证行为正确。
3. **准确度 > 性能** — 工具的结果准确性是底线。宁可慢一点也不能出错。
4. **简单直接** — 不过度设计，不提前抽象。三行重复代码好过一个过早的抽象。

---

## 架构规范

### 代码分层

```
cody/
├── core/           # 引擎核心（不依赖 CLI 或 Server）
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
│   ├── auth.py         # OAuth 认证（HMAC-SHA256 token）
│   ├── permissions.py  # 工具级权限（allow/deny/confirm）
│   ├── file_history.py # 文件 undo/redo 快照
│   └── rate_limiter.py # 滑动窗口限流
├── skills/         # 内置 Skills（git, github, docker, npm, python）
├── server.py       # RPC Server（FastAPI），调用 core
├── tui.py          # TUI 界面（Textual），调用 core
└── cli.py          # CLI 界面（Click），调用 core
```

**关键约束：**
- `core/` 内的代码 **不允许** 导入 `cli.py` 或 `server.py`
- `cli.py` 和 `server.py` 都通过 `core/` 提供的接口工作
- 新功能应该加在 `core/`，然后分别在 Server 和 CLI 暴露

### 依赖方向

```
cli.py ──→ core/ ←── server.py
              ↓
          pydantic-ai, sqlite3, etc.
```

禁止反向依赖。禁止 `core/` 依赖任何 CLI（click, rich）或 Server（fastapi）的库。

---

## 测试规范

### 必须测试

| 变更类型 | 测试要求 |
|----------|----------|
| 新工具（tools.py） | 至少 3 个测试：正常路径、边界情况、错误处理 |
| 新 API 端点（server.py） | 至少 2 个测试：正常响应、错误响应 |
| 新 CLI 命令（cli.py） | 至少 1 个测试：基本调用 |
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

### Server 测试用法

```python
from fastapi.testclient import TestClient
from cody.server import app

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
- **Python 版本** — 3.9+（不用 3.10+ 语法如 `match/case`）
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
3. **Server 端点** — 在 `server.py` 暴露 API
4. **CLI 命令** — 在 `cli.py` 提供界面（如果需要）
5. **运行测试** — 全部通过
6. **运行 lint** — 零告警

### 示例：添加新工具

```
1. 在 core/tools.py 实现工具函数
2. 在 tests/test_tools.py 写 3+ 个测试
3. 在 core/runner.py 注册工具
4. 在 server.py 的 /tool 端点确认可调用
5. pytest + ruff 通过
```

---

## 当前状态

| 模块 | 测试数 | 状态 |
|------|--------|------|
| core/tools.py | 51 | 完善 |
| core/lsp_client.py | 34 | 完善 |
| server.py | 32 | 完善 |
| core/web.py | 22 | 完善 |
| core/sub_agent.py | 22 | 完善 |
| client.py | 19 | 完善 |
| client retry | 18 | 完善 |
| core/context.py | 16 | 完善 |
| cli.py | 16 | 基本覆盖 |
| core/config.py | 15 | 完善 |
| core/skill_manager.py | 14 | 完善 |
| core/session.py | 14 | 完善 |
| core/mcp_client.py | 15 | 完善 |
| core/runner.py | 12 | 完善 |
| core/errors.py | 11 | 完善 |
| core/audit.py | 16 | 完善 |
| core/auth.py | 14 | 完善 |
| core/permissions.py | 14 | 完善 |
| core/file_history.py | 16 | 完善 |
| core/rate_limiter.py | 12 | 完善 |
| tui.py | 10 | 基本覆盖 |
| WebSocket | 7 | 基本覆盖 |

**总计：418 个测试，ruff 零告警**

**当前版本：v1.1.0（见 docs/FEATURES.md 版本记录）**
