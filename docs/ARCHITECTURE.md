# Cody - Architecture Design

## 系统架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                        用户/调用方                            │
│         (CLI / Clawdbot / CI/CD / 其他 Agent)                │
└─────────────┬───────────────────────────────────────────────┘
              │
              ├─ CLI 模式 (cody)
              │     ↓
              │  Click CLI → Agent Runner
              │
              └─ RPC 模式 (cody-server)
                    ↓
                  FastAPI → Agent Runner
              │
              ↓
┌─────────────────────────────────────────────────────────────┐
│                      Cody Core Engine                        │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Pydantic AI Agent                        │  │
│  │  (Core orchestration + LLM interaction)               │  │
│  └───────────────────────────────────────────────────────┘  │
│                          ↓                                   │
│  ┌───────────────────────────────────────────────────────┐  │
│  │           Tool & Skill Manager                        │  │
│  │  ┌──────────────┬────────────────┬─────────────────┐ │  │
│  │  │ Built-in     │ Skill System   │ MCP Client      │ │  │
│  │  │ Tools        │                │                 │ │  │
│  │  │ - file ops   │ - .cody/skills │ - External      │ │  │
│  │  │ - exec       │ - ~/.cody/     │   MCP Servers   │ │  │
│  │  │ - git        │ - builtin/     │                 │ │  │
│  │  └──────────────┴────────────────┴─────────────────┘ │  │
│  └───────────────────────────────────────────────────────┘  │
│                          ↓                                   │
│  ┌───────────────────────────────────────────────────────┐  │
│  │          Sub-Agent Manager (Optional)                 │  │
│  │  - Spawn specialized agents                           │  │
│  │  - Manage agent lifecycle                             │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────────────────────┐
│                  External Services                           │
│  - Anthropic API (Claude)                                   │
│  - OpenAI API                                               │
│  - File System                                              │
│  - Shell Commands                                           │
│  - MCP Servers                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 核心组件

### 1. Agent Runner

**职责：**
- 管理 Pydantic AI Agent 实例
- 处理会话状态
- 协调工具调用
- 管理配置和认证

**代码结构：**
```python
# core/runner.py
class AgentRunner:
    def __init__(self, config: Config):
        self.config = config
        self.agent = self._create_agent()
        self.skill_manager = SkillManager()
        self.mcp_client = MCPClient()
        self.sub_agent_manager = SubAgentManager()
    
    async def run(self, prompt: str, context: RunContext) -> Result:
        # 1. 加载配置和 skills
        # 2. 初始化 Agent
        # 3. 运行任务
        # 4. 返回结果
        pass
```

### 2. Skill Manager

**职责：**
- 扫描和加载 Skills
- 管理 Skill 优先级
- 提供 Skill 查询接口

**优先级：**
1. `.cody/skills/` - 项目级
2. `~/.cody/skills/` - 用户级
3. `{install}/skills/` - 内置

**代码结构：**
```python
# core/skill_manager.py
class SkillManager:
    def __init__(self):
        self.skills = {}
        self._load_skills()
    
    def _load_skills(self):
        # 按优先级扫描三个目录
        for path in [project_skills, user_skills, builtin_skills]:
            self._scan_directory(path)
    
    def get_skill(self, name: str) -> Skill:
        return self.skills.get(name)
    
    def list_skills(self) -> list[str]:
        return list(self.skills.keys())
```

### 3. Tool System

**内置工具：**
```python
# core/tools/file.py
@cody_agent.tool
async def read_file(ctx: RunContext, path: str) -> str:
    """Read file contents"""
    full_path = resolve_path(ctx.workdir, path)
    validate_access(full_path)
    return Path(full_path).read_text()

@cody_agent.tool
async def write_file(ctx: RunContext, path: str, content: str) -> str:
    """Write content to file"""
    full_path = resolve_path(ctx.workdir, path)
    validate_access(full_path)
    Path(full_path).write_text(content)
    return f"Written to {path}"
```

**Skill 元工具：**
```python
# core/tools/skill.py
@cody_agent.tool
async def list_skills(ctx: RunContext) -> list[str]:
    """List available skills"""
    return ctx.skill_manager.list_skills()

@cody_agent.tool
async def read_skill(ctx: RunContext, skill_name: str) -> str:
    """Read skill documentation"""
    skill = ctx.skill_manager.get_skill(skill_name)
    return skill.read_documentation()
```

### 4. MCP Client

**职责：**
- 连接和管理 MCP Servers
- 代理工具调用
- 处理 Server 生命周期

**代码结构：**
```python
# core/mcp_client.py
from pydantic_ai.mcp import MCPServer

class MCPClient:
    def __init__(self, config: MCPConfig):
        self.servers = {}
        self._load_servers(config)
    
    async def connect_server(self, name: str, server_config: dict):
        server = MCPServer(
            command=server_config['command'],
            args=server_config['args'],
            env=server_config.get('env', {})
        )
        await server.start()
        self.servers[name] = server
    
    async def call_tool(self, server: str, tool: str, params: dict):
        return await self.servers[server].call_tool(tool, params)
```

### 5. Sub-Agent Manager

**职责：**
- 创建和管理子 Agent
- 追踪子 Agent 状态
- 资源管理和清理

**代码结构：**
```python
# core/sub_agent.py
class SubAgentManager:
    def __init__(self):
        self.agents = {}  # agent_id -> Agent
    
    async def spawn(self, task: str, agent_type: str) -> str:
        """Spawn a sub-agent"""
        agent_id = uuid.uuid4().hex
        
        # 创建专门化的 Agent
        agent = self._create_agent_by_type(agent_type)
        
        # 后台运行
        asyncio.create_task(self._run_agent(agent_id, agent, task))
        
        return agent_id
    
    async def _run_agent(self, agent_id: str, agent: Agent, task: str):
        try:
            result = await agent.run(task)
            self.agents[agent_id] = {
                'status': 'completed',
                'result': result.output
            }
        except Exception as e:
            self.agents[agent_id] = {
                'status': 'failed',
                'error': str(e)
            }
```

---

## 数据流

### CLI 模式

```
用户输入
  ↓
Click CLI (cli.py)
  ↓
AgentRunner.run(prompt, workdir)
  ↓
Pydantic AI Agent
  ↓ (tool calls)
Tool Manager → File/Exec/Skill/MCP
  ↓ (results)
Agent → LLM → Final Output
  ↓
显示结果
```

### RPC 模式

```
HTTP Request (POST /run)
  ↓
FastAPI Handler (server.py)
  ↓
AgentRunner.run(prompt, context)
  ↓
Pydantic AI Agent
  ↓ (tool calls)
Tool Manager
  ↓ (results)
Agent → LLM → Final Output
  ↓
JSON Response / SSE Stream
```

### 子 Agent 模式

```
主 Agent 判断需要孵化
  ↓
调用 spawn_agent(task, type) 工具
  ↓
SubAgentManager.spawn()
  ↓
创建新 Agent 实例（独立工具集）
  ↓
后台运行（asyncio.create_task）
  ↓
完成后返回结果给主 Agent
  ↓
主 Agent 整合结果继续执行
```

---

## 配置系统

### 配置加载顺序

1. 内置默认配置
2. 全局配置 `~/.cody/config.json`
3. 项目配置 `.cody/config.json`
4. 命令行参数
5. 环境变量

**合并策略：** 后加载的覆盖先加载的

### 配置结构

```python
# core/config.py
from pydantic import BaseModel

class AuthConfig(BaseModel):
    type: Literal['oauth', 'api_key']
    token: str | None = None
    refresh_token: str | None = None
    api_key: str | None = None
    expires_at: datetime | None = None

class SkillConfig(BaseModel):
    enabled: list[str] = []
    disabled: list[str] = []

class MCPServerConfig(BaseModel):
    name: str
    command: str
    args: list[str]
    env: dict[str, str] = {}

class MCPConfig(BaseModel):
    servers: list[MCPServerConfig] = []

class SecurityConfig(BaseModel):
    allowed_commands: list[str] | None = None
    restricted_paths: list[str] = []
    require_confirmation: bool = True

class Config(BaseModel):
    model: str = 'anthropic:claude-sonnet-4-0'
    auth: AuthConfig
    skills: SkillConfig = SkillConfig()
    mcp: MCPConfig = MCPConfig()
    security: SecurityConfig = SecurityConfig()
```

---

## 安全设计

### 1. 命令执行安全

**白名单机制：**
```python
ALLOWED_COMMANDS = ['git', 'npm', 'python', 'pip', 'docker']

def validate_command(command: str) -> bool:
    base_cmd = command.split()[0]
    return base_cmd in ALLOWED_COMMANDS
```

**危险命令拦截：**
```python
DANGEROUS_PATTERNS = [
    r'rm\s+-rf\s+/',
    r'dd\s+if=.*of=/dev/',
    r':\(\)\{.*\}',  # fork bomb
]

def is_dangerous(command: str) -> bool:
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command):
            return True
    return False
```

### 2. 文件访问控制

**路径验证：**
```python
def validate_file_access(path: str, workdir: str) -> bool:
    resolved = Path(path).resolve()
    workdir_resolved = Path(workdir).resolve()
    
    # 必须在工作目录内
    return resolved.is_relative_to(workdir_resolved)
```

### 3. 资源限制

**子 Agent 限制：**
```python
MAX_SUB_AGENTS = 5
MAX_AGENT_RUNTIME = 300  # 5分钟

async def spawn(self, task: str) -> str:
    if len(self.agents) >= MAX_SUB_AGENTS:
        raise TooManyAgentsError()
    
    # 设置超时
    async with asyncio.timeout(MAX_AGENT_RUNTIME):
        result = await agent.run(task)
```

---

## 性能优化

### 1. 缓存策略

**Skill 文档缓存：**
```python
from functools import lru_cache

@lru_cache(maxsize=128)
def load_skill_doc(skill_path: str) -> str:
    return Path(skill_path).read_text()
```

**模型响应缓存（可选）：**
```python
# 对于确定性任务
cache_key = f"{prompt}:{tools}:{model}"
if cache_key in cache:
    return cache[cache_key]
```

### 2. 并发处理

**工具并行调用：**
```python
# Pydantic AI 自动支持并行工具调用
# 当 LLM 返回多个工具调用时，会并发执行
```

**子 Agent 并行：**
```python
tasks = [
    spawn_agent("task1", "code"),
    spawn_agent("task2", "research")
]
results = await asyncio.gather(*tasks)
```

---

## 扩展性设计

### 1. 插件系统

**未来支持：**
```python
# plugins/custom_tool.py
from cody import Tool

class CustomTool(Tool):
    name = "my_tool"
    description = "Custom tool"
    
    async def run(self, ctx: RunContext, **kwargs):
        # 实现
        pass

# 注册
cody.register_plugin(CustomTool())
```

### 2. 自定义模型

**支持自定义模型：**
```python
from pydantic_ai.models import Model

class CustomModel(Model):
    async def request(...):
        # 实现
        pass

agent = Agent(CustomModel())
```

---

## 测试策略

### 1. 单元测试

```python
# tests/test_tools.py
async def test_read_file():
    ctx = create_test_context()
    result = await read_file(ctx, "test.txt")
    assert "content" in result
```

### 2. 集成测试

```python
# tests/test_agent.py
async def test_agent_flow():
    agent = create_test_agent()
    result = await agent.run("Create hello.py")
    assert Path("hello.py").exists()
```

### 3. RPC 测试

```python
# tests/test_server.py
async def test_api_endpoint():
    client = TestClient(app)
    response = client.post("/run", json={
        "prompt": "test task"
    })
    assert response.status_code == 200
```

---

## 部署

### 开发环境
```bash
pip install -e .
cody-server --reload
```

### 生产环境
```bash
# Docker
docker run -p 8000:8000 cody:latest

# systemd
systemctl start cody-server
```

---

**最后更新：** 2026-01-28
