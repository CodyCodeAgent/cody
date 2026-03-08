# Cody - 技能开发指南

技能（Skills）是 Cody 框架的核心组件之一，遵循 [Agent Skills Open Standard](https://agentskills.io/) 规范（已被 26+ 平台采用，包括 Claude Code、Cursor、GitHub Copilot 等）。通过技能，你可以为 AI Agent 提供特定领域的专业知识和最佳实践。

> **跨平台兼容**：基于 Cody 框架创建的技能可以直接在其他支持 Agent Skills 标准的平台上使用，反之亦然。

---

## 什么是技能？

技能是一个 Markdown 文件（`SKILL.md`），包含：
- **YAML Frontmatter** — 元数据（名称、描述、许可证等）
- **Markdown 正文** — 详细的指令和示例

AI 会根据任务上下文自动激活相关技能，并遵循技能中的指令。

---

## 技能结构

### 基本格式

```markdown
---
name: skill-name
description: 简短描述技能的用途
license: MIT  # 可选
compatibility: claude-code,codex-cli,cursor  # 可选
metadata:
  author: your-name
  version: "1.0"
allowed-tools: read_file,exec_command  # 可选，限制技能可使用的工具
---

# 技能名称

这里是技能的详细指令和示例...
```

### Frontmatter 字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | ✅ | 技能名称（小写，字母数字 + 连字符） |
| `description` | ✅ | 简短描述（≤1024 字符） |
| `license` | ❌ | 许可证（MIT、Apache-2.0 等） |
| `compatibility` | ❌ | 兼容平台列表 |
| `metadata` | ❌ | 自定义元数据（作者、版本等） |
| `allowed-tools` | ❌ | 技能推荐使用的工具列表 |

### 命名规则

- 只能使用小写字母、数字和连字符
- 不能以连字符开头或结尾
- 不能有连续的连字符
- 必须与目录名匹配

**有效名称:**
```
git
github-actions
python-testing
docker-compose
```

**无效名称:**
```
Git          # 不能大写
git_test     # 不能用下划线
-git         # 不能以连字符开头
git--test    # 不能有连续连字符
```

---

## 创建技能

### 步骤 1：创建技能目录

技能可以放在三个位置（优先级从高到低）：

1. **项目级** — `.cody/skills/<skill-name>/`
2. **用户级** — `~/.cody/skills/<skill-name>/`
3. **内置** — `{install}/skills/<skill-name>/`

```bash
# 项目级技能
mkdir -p .cody/skills/my-skill

# 用户级技能
mkdir -p ~/.cody/skills/my-skill
```

### 步骤 2：创建 SKILL.md

```bash
# 创建技能文件
cat > .cody/skills/my-skill/SKILL.md << 'EOF'
---
name: my-skill
description: 我的自定义技能
metadata:
  author: your-name
  version: "1.0"
---

# My Skill

这里是技能指令...
EOF
```

### 步骤 3：验证技能

```bash
# 列出技能
cody skills list

# 查看技能文档
cody skills show my-skill
```

---

## 技能内容编写

### 最佳实践

1. **清晰的标题** — 使用 Markdown 标题组织内容
2. **分步骤指令** — 使用编号列表
3. **代码示例** — 使用代码块展示示例
4. **注意事项** — 使用引用块强调重点
5. **先决条件** — 明确说明前置要求

### 示例结构

```markdown
---
name: python-testing
description: Python 测试最佳实践
---

# Python Testing Skill

Python 单元测试和集成测试的最佳实践。

## 先决条件

- Python 3.10+
- pytest 安装：`pip install pytest`

## 测试文件命名

测试文件应以 `test_` 开头或 `_test.py` 结尾：
- `test_user_service.py`
- `user_service_test.py`

## 测试函数命名

测试函数应以 `test_` 开头：

```python
def test_user_creation():
    """测试用户创建"""
    pass

def test_login_with_valid_credentials():
    """测试有效凭据登录"""
    pass
```

## 断言最佳实践

1. **一个测试一个断言** — 每个测试函数只验证一件事
2. **使用描述性消息** — 断言失败时易于理解

```python
def test_user_age():
    user = User(age=25)
    assert user.age == 25, "User age should be 25"
```

## 使用 pytest fixture

```python
import pytest

@pytest.fixture
def sample_user():
    return User(name="Alice", age=30)

def test_user_name(sample_user):
    assert sample_user.name == "Alice"
```

## 运行测试

```bash
# 运行所有测试
pytest

# 运行特定文件
pytest tests/test_user.py

# 运行特定测试
pytest tests/test_user.py::test_user_name

# 显示覆盖率
pytest --cov=src
```

## 注意事项

- 测试不应该有副作用
- 测试应该是可重复的
- 避免测试实现细节，测试行为
```

---

## 内置技能参考

Cody 自带 11 个内置技能：

| 技能 | 说明 |
|------|------|
| `git` | Git 版本控制操作 |
| `github` | GitHub 集成（PR、Issue 等） |
| `docker` | Docker 容器管理 |
| `npm` | Node.js 包管理 |
| `python` | Python 开发最佳实践 |
| `rust` | Rust 开发最佳实践 |
| `go` | Go 开发最佳实践 |
| `java` | Java 开发（Maven/Gradle） |
| `web` | Web 搜索和抓取 |
| `cicd` | CI/CD 配置（GitHub Actions 等） |
| `testing` | 通用测试最佳实践 |

### 查看内置技能

```bash
# 列出所有技能
cody skills list

# 查看技能文档
cody skills show git
cody skills show python
```

---

## 技能启用/禁用

### 临时启用/禁用

```bash
# 启用技能
cody skills enable my-skill

# 禁用技能
cody skills disable my-skill
```

### 配置文件中管理

在 `.cody/config.json` 或 `~/.cody/config.json` 中：

```json
{
  "skills": {
    "enabled": ["git", "github", "my-skill"],
    "disabled": ["docker"]
  }
}
```

**优先级规则：**
1. `disabled` 列表中的技能始终禁用
2. 如果 `enabled` 非空，只启用列表中的技能
3. 如果 `enabled` 为空，默认启用所有技能

---

## 技能使用场景

### 场景 1：项目特定规范

为项目创建自定义编码规范：

```markdown
---
name: project-style
description: 项目编码规范
---

# Project Style Guide

## 代码风格

- 使用 4 空格缩进
- 函数名使用 snake_case
- 类名使用 PascalCase

## 文件组织

- 所有模块放在 src/ 目录
- 测试放在 tests/ 目录
- 文档放在 docs/ 目录

## 提交规范

提交信息格式：`<类型>: <描述>`

类型包括：
- feat: 新功能
- fix: Bug 修复
- docs: 文档更新
- style: 代码风格
- refactor: 重构
- test: 测试
- chore: 构建/工具
```

### 场景 2：框架最佳实践

为特定框架创建使用指南：

```markdown
---
name: fastapi-skill
description: FastAPI 框架最佳实践
---

# FastAPI Skill

## 项目结构

```
myapp/
├── main.py
├── config.py
├── models/
│   ├── __init__.py
│   └── user.py
├── schemas/
│   ├── __init__.py
│   └── user.py
├── routers/
│   ├── __init__.py
│   └── users.py
└── dependencies.py
```

## 依赖注入

```python
from fastapi import Depends

def get_db():
    db = Database()
    try:
        yield db
    finally:
        db.close()

@app.get("/users/{user_id}")
async def get_user(user_id: int, db: Session = Depends(get_db)):
    ...
```

## 错误处理

```python
from fastapi import HTTPException

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
```
```

### 场景 3：团队工作流

为团队创建协作规范：

```markdown
---
name: team-workflow
description: 团队协作工作流
---

# Team Workflow

## Git 分支策略

- `main` — 生产分支，受保护
- `develop` — 开发分支
- `feature/*` — 功能分支
- `fix/*` — 修复分支
- `release/*` — 发布分支

## Code Review 流程

1. 创建 PR 到 `develop` 分支
2. 至少需要 1 人 review
3. 所有 CI 检查必须通过
4.  squash merge 到 `develop`

## 发布流程

1. 从 `develop` 创建 `release/vX.Y.Z`
2. 测试验证
3. merge 到 `main` 并打 tag
4. merge 回 `develop`
```

---

## 技能测试

### 验证技能格式

```bash
# 查看技能是否正确加载
cody skills list

# 应该看到：
# [on] my-skill (project)
#       我的自定义技能
```

### 测试技能效果

```bash
# 使用技能执行任务
cody run "按照项目规范创建一个新用户模块"

# 观察 AI 是否遵循技能中的指令
```

---

## 技能分发

### 分享技能

将技能目录打包分享：

```bash
# 打包技能
tar -czf my-skill.tar.gz .cody/skills/my-skill/

# 分享给团队成员
scp my-skill.tar.gz teammate:/path/to/project/

# 队友解压
tar -xzf my-skill.tar.gz -C .cody/skills/
```

### 技能仓库

可以创建 Git 仓库管理技能集合：

```bash
# 创建技能仓库
git init cody-skills
cd cody-skills

# 添加技能
mkdir -p skills/python-testing skills/fastapi
# ... 创建 SKILL.md 文件

# 提交
git add .
git commit -m "Add Python testing and FastAPI skills"
```

---

## 高级用法

### 技能组合

多个技能可以同时启用，AI 会根据上下文选择使用：

```bash
# 启用多个技能
cody skills enable python-testing
cody skills enable fastapi-skill
cody skills enable project-style

# AI 会自动组合使用相关技能
cody run "创建一个用户 API，包含测试"
```

### 技能优先级

技能按以下优先级加载（高优先级覆盖低优先级）：

1. **项目级** — `.cody/skills/`
2. **用户级** — `~/.cody/skills/`
3. **内置** — `{install}/skills/`

同名技能，高优先级的会覆盖低优先级的。

### 条件激活

技能可以通过描述和元数据提示 AI 何时激活：

```markdown
---
name: react-skill
description: React 开发最佳实践。当任务涉及 React、JSX、组件时使用。
compatibility: cursor,codex-cli
---

# React Skill

仅在任务涉及 React 开发时激活...
```

---

## 常见问题

### Q: 技能名称必须和目录名一致吗？

是的，`name` 字段必须与目录名完全匹配。

### Q: 技能文件可以放在其他地方吗？

不可以，必须放在 `skills/` 目录下的子目录中。

### Q: 如何禁用内置技能？

在配置文件中添加到 `disabled` 列表：
```json
{
  "skills": {
    "disabled": ["docker", "java"]
  }
}
```

### Q: 技能有大小限制吗？

建议技能文档控制在 10KB 以内，过大会影响加载速度。

### Q: 技能可以使用图片吗？

不建议，技能应该是纯文本 Markdown。

### Q: 如何调试技能问题？

```bash
# 查看技能是否正确加载
cody skills list

# 查看技能详细内容
cody skills show <skill-name>

# 检查技能文件格式
cat .cody/skills/<skill-name>/SKILL.md
```

---

## Agent Skills 开放标准

Cody 遵循 [Agent Skills Open Standard](https://agentskills.io/)，该标准已被 26+ 平台采用：

- Claude Code
- Codex CLI
- Cursor
- GitHub Copilot
- 等等

### 标准优势

1. **跨平台兼容** — 技能可以在不同平台间共享
2. **渐进式披露** — 只加载元数据，完整内容按需加载
3. **上下文注入** — 技能 XML 自动注入系统提示
4. **版本管理** — 支持技能版本和许可证

### 标准格式

```yaml
---
name: skill-name
description: Short description
license: MIT
compatibility: platform1,platform2
metadata:
  author: name
  version: "1.0"
---

# Skill Instructions

Detailed instructions...
```

---

## SDK 中使用技能

除了 CLI 管理技能，你也可以通过 Python SDK 程序化管理：

```python
from cody import AsyncCodyClient

async with AsyncCodyClient(workdir="/path/to/project") as client:
    # 列出所有技能
    skills = await client.list_skills()
    for skill in skills:
        print(f"[{'on' if skill['enabled'] else 'off'}] {skill['name']}: {skill['description']}")

    # 获取技能文档
    skill = await client.get_skill("git")
    print(skill['documentation'])

    # 指定启用的技能执行任务
    result = await client.run("创建一个用户 API，包含测试")
    print(result.output)
```

更多 SDK 用法详见 [SDK 使用文档](SDK.md)。

---

## 贡献内置技能

欢迎贡献新的内置技能！

### 提交流程

1. Fork [项目仓库](https://github.com/CodyCodeAgent/cody)
2. 在 `cody/skills/` 下创建技能目录
3. 创建 `SKILL.md` 文件
4. 运行测试验证
5. 提交 Pull Request

### 审核标准

- 遵循 Agent Skills 标准格式
- 内容清晰、准确、有用
- 代码示例正确
- 无拼写和语法错误

---

**最后更新:** 2026-03-04
