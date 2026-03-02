# Cody - 快速入门教程

欢迎使用 Cody！本教程将带你从零开始，快速上手使用 Cody 完成实际开发任务。

---

## 1. 安装 Cody

### 系统要求

- Python 3.9+
- pip 包管理器
- Git（可选，用于版本控制）

### 安装步骤

```bash
# 克隆项目
git clone https://github.com/SUT-GC/cody.git
cd cody

# 安装
pip install -e .

# 验证安装
cody --version
```

看到版本号表示安装成功！

---

## 2. 配置 API Key

Cody 需要访问大模型 API。以下是几种配置方式：

### 方式 1：Anthropic（默认）

```bash
# 获取 API Key: https://console.anthropic.com/
export ANTHROPIC_API_KEY='sk-ant-...'
```

### 方式 2：智谱 GLM

```bash
export CODY_MODEL='glm-4'
export CODY_MODEL_BASE_URL='https://open.bigmodel.cn/api/paas/v4/'
export CODY_MODEL_API_KEY='sk-...'
```

### 方式 3：阿里云通义千问

```bash
export CODY_MODEL='qwen-coder-plus'
export CODY_MODEL_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
export CODY_MODEL_API_KEY='sk-...'
```

### 方式 4：阿里云百炼 Coding Plan

```bash
export CODY_MODEL='qwen3.5'
export CODY_CODING_PLAN_KEY='sk-sp-...'
```

### 验证配置

```bash
# 查看当前配置
cody config show
```

---

## 3. 第一个任务

让我们用 Cody 创建第一个文件：

```bash
cody run "创建一个 Python 脚本，打印 Hello World"
```

**输出示例：**
```
  → write_file(path='hello.py')
  → exec_command(command='python3 hello.py')

已创建 hello.py 文件：

```python
print("Hello World!")
```

运行结果：
```
Hello World!
```
```

查看创建的文件：
```bash
cat hello.py
```

---

## 4. 使用 CLI 完成任务

### 任务 1：创建 FastAPI 项目

```bash
cody run "创建一个 FastAPI 项目，包含以下功能：
- / 端点返回欢迎消息
- /health 端点返回健康状态
- 使用 uvicorn 运行"
```

**预期输出：**
```
  → write_file(path='main.py')
  → write_file(path='requirements.txt')

已创建 FastAPI 项目：

main.py:
```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Welcome to FastAPI!"}

@app.get("/health")
async def health():
    return {"status": "ok"}
```

requirements.txt:
```
fastapi
uvicorn
```

运行：`uvicorn main:app --reload`
```

### 任务 2：添加功能

```bash
cody run "在 main.py 中添加一个 /users/{user_id} 端点，返回用户信息"
```

### 任务 3：编写测试

```bash
cody run "为 main.py 编写 pytest 测试"
```

---

## 5. 交互式对话

使用 `chat` 命令进行多轮对话：

```bash
cody chat
```

**对话示例：**
```
╭────────────────────────────────────────────────────╮
│                  Cody Chat                          │
│  Model: anthropic:claude-sonnet-4-0                │
│  Workdir: /home/user/myproject                     │
│  Session: abc123                                   │
╰────────────────────────────────────────────────────╯

You > 帮我创建一个 Flask 应用

  → write_file(path='app.py')
  → write_file(path='requirements.txt')

已创建 Flask 应用...

You > 添加一个登录端点

  → edit_file(path='app.py')

已添加 /login 端点...

You > 添加 JWT 认证

  → edit_file(path='app.py')
  → write_file(path='auth.py')

已添加 JWT 认证...

You > /quit
Bye!
```

### 斜杠命令

```
/sessions    # 列出会话
/clear       # 清屏
/help        # 显示帮助
/quit        # 退出
```

---

## 6. 使用 TUI

启动全屏终端界面：

```bash
cody tui
```

**界面：**
```
┌─────────────────────────────────────────────────┐
│  Cody                              [Header]     │
├─────────────────────────────────────────────────┤
│  You > 创建项目                                 │
│  Cody > 已创建...                               │
│                                                 │
│  [对话历史 - 可滚动]                             │
│                                                 │
├─────────────────────────────────────────────────┤
│  Session: abc123 | Model: ... | Msgs: 2        │
├─────────────────────────────────────────────────┤
│  You > [输入框]                                 │
├─────────────────────────────────────────────────┤
│  Ctrl+N New  Ctrl+C Cancel  Ctrl+Q Quit        │
└─────────────────────────────────────────────────┘
```

**快捷键：**
- `Ctrl+N` — 新建会话
- `Ctrl+C` — 取消/退出
- `Ctrl+Q` — 退出

---

## 7. 使用技能

技能提供特定领域的专业知识。

### 查看可用技能

```bash
cody skills list
```

**输出：**
```
Available Skills:

  [on] git        (builtin)
        Git version control operations...
  [on] github     (builtin)
        GitHub integration...
  [on] docker     (builtin)
        Docker container management...
  [on] python     (builtin)
        Python development...
```

### 使用技能

```bash
# 查看技能文档
cody skills show git

# 启用技能
cody skills enable python

# 使用技能执行任务
cody run "按照 Python 最佳实践重构这个模块"
```

---

## 8. 会话管理

### 列出会话

```bash
cody sessions list
```

**输出：**
```
Recent sessions:

  abc123  Flask 应用开发                      4 msgs  2026-02-28
  def456  代码重构                            8 msgs  2026-02-27
```

### 查看会话

```bash
cody sessions show abc123
```

### 恢复会话

```bash
# 继续上次会话
cody chat --continue

# 恢复指定会话
cody chat --session abc123
```

### 删除会话

```bash
cody sessions delete abc123
```

---

## 9. 实战项目

让我们完成一个完整的项目：

### 步骤 1：初始化项目

```bash
mkdir myproject
cd myproject
cody init
```

### 步骤 2：创建项目结构

```bash
cody run "创建一个 Python 项目结构，包含：
- src/ 目录放源代码
- tests/ 目录放测试
- docs/ 目录放文档
- pyproject.toml 配置
- README.md 说明文件"
```

### 步骤 3：实现功能

```bash
cody run "在 src/ 下创建一个计算器模块，支持加减乘除"
```

### 步骤 4：编写测试

```bash
cody run "为计算器模块编写完整的单元测试"
```

### 步骤 5：运行测试

```bash
cody run "运行所有测试并修复失败"
```

### 步骤 6：添加文档

```bash
cody run "为计算器模块编写 API 文档"
```

---

## 10. 使用 SDK

### Python SDK

SDK 是 in-process 封装，直接调用核心引擎，无需启动 Server。

```python
from cody import AsyncCodyClient

async with AsyncCodyClient(workdir="/path/to/project") as client:
    # 单次任务
    result = await client.run("创建 hello.py")
    print(result.output)

    # 多轮对话
    session = await client.create_session()
    await client.run("创建 Flask 应用", session_id=session.id)
    await client.run("添加 /health 端点", session_id=session.id)

    # 流式输出
    async for chunk in client.stream("解释代码"):
        print(chunk.content, end="")
```

---

## 11. 启动 Web

```bash
# 启动统一服务器（RPC API + Web 功能）
cody-web --port 8000

# 访问 API 文档
open http://localhost:8000/docs
```

**API 端点：**
- `POST /run` — 执行任务
- `POST /run/stream` — 流式执行
- `GET /skills` — 列出技能
- `GET /sessions` — 列出会话
- `GET /health` — 健康检查

---

## 12. 最佳实践

### 1. 明确工作目录

```bash
# 推荐
cody run "任务" --workdir /path/to/project

# 不推荐（依赖当前目录）
cd /path/to/project && cody run "任务"
```

### 2. 使用会话进行多轮对话

```bash
# 第一次
cody chat --workdir /path/to/project

# 继续
cody chat --continue
```

### 3. 复杂任务启用思考模式

```bash
cody run --thinking "分析项目架构问题"
```

### 4. 查看详细输出

```bash
cody run -v "任务"  # 显示工具调用结果
```

### 5. 使用技能

```bash
# 启用相关技能
cody skills enable git
cody skills enable python

# 执行任务
cody run "按照最佳实践重构代码"
```

---

## 13. 常见问题

### Q: 安装失败怎么办？

```bash
# 升级 pip
pip install --upgrade pip

# 使用虚拟环境
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Q: API Key 错误？

检查环境变量：
```bash
echo $ANTHROPIC_API_KEY
```

确保 Key 正确且未过期。

### Q: 任务执行慢？

- 检查网络连接
- 使用较小的任务
- 启用思考模式查看进度

### Q: 如何查看日志？

```bash
# 审计日志
~/.cody/audit.db

# 会话数据
~/.cody/sessions.db
```

---

## 14. 下一步

完成本教程后，你可以：

1. **阅读详细文档**
   - [CLI 使用文档](docs/CLI.md)
   - [SDK 使用文档](docs/SDK.md)
   - [TUI 使用文档](docs/TUI.md)
   - [技能开发指南](docs/SKILLS.md)

2. **探索高级功能**
   - MCP 集成
   - LSP 代码智能
   - 子代理系统
   - 自定义技能

3. **参与社区**
   - 提交 Issue
   - 贡献代码
   - 分享技能

---

## 15. 获取帮助

```bash
# CLI 帮助
cody --help
cody run --help
cody chat --help

# 查看配置
cody config show

# 列出技能
cody skills list
```

**文档资源：**
- README.md — 项目概述
- docs/CLI.md — CLI 详细用法
- docs/API.md — RPC API 文档
- docs/ARCHITECTURE.md — 架构设计
- CONTRIBUTING.md — 开发规范

---

祝你使用愉快！🎉

**最后更新:** 2026-02-28
