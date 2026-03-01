# Cody - 配置文件详解

Cody 使用 JSON 配置文件，支持多层级配置和运行时覆盖。本文详细介绍所有配置项。

---

## 配置文件位置

配置文件按以下优先级加载（后加载覆盖先加载）：

1. **内置默认值** — Pydantic 模型默认值
2. **全局配置** — `~/.cody/config.json`
3. **项目配置** — `.cody/config.json`
4. **环境变量** — `CODY_*` 系列变量
5. **CLI 参数** — 命令行标志

---

## 配置文件结构

```json
{
  "model": "anthropic:claude-sonnet-4-0",
  "model_base_url": null,
  "model_api_key": null,
  "claude_oauth_token": null,
  "coding_plan_key": null,
  "coding_plan_protocol": "openai",
  "enable_thinking": false,
  "thinking_budget": null,
  "auth": {
    "type": "api_key",
    "token": null,
    "refresh_token": null,
    "api_key": null,
    "expires_at": null
  },
  "skills": {
    "enabled": ["git", "github"],
    "disabled": []
  },
  "mcp": {
    "servers": []
  },
  "permissions": {
    "overrides": {},
    "default_level": "confirm"
  },
  "security": {
    "allowed_commands": null,
    "restricted_paths": [],
    "require_confirmation": true
  },
  "rate_limit": {
    "enabled": false,
    "max_requests": 60,
    "window_seconds": 60.0
  }
}
```

---

## 配置项详解

### 模型配置

#### `model`

**类型:** `string`  
**默认:** `"anthropic:claude-sonnet-4-0"`  
**说明:** AI 模型名称

```json
{
  "model": "anthropic:claude-sonnet-4-0"
}
```

**支持的模型：**
- `anthropic:claude-sonnet-4-0`
- `anthropic:claude-opus-4-0`
- `openai:gpt-4`
- `openai:gpt-4-turbo`
- `google:gemini-pro`
- `deepseek:deepseek-coder`
- 任何 OpenAI 兼容模型

---

#### `model_base_url`

**类型:** `string | null`  
**默认:** `null`  
**说明:** 自定义 OpenAI 兼容 API 地址

```json
{
  "model": "glm-4",
  "model_base_url": "https://open.bigmodel.cn/api/paas/v4/"
}
```

**使用场景：**
- 智谱 GLM: `https://open.bigmodel.cn/api/paas/v4/`
- 阿里通义：`https://dashscope.aliyuncs.com/compatible-mode/v1`
- 本地部署：`http://localhost:8000/v1`

---

#### `model_api_key`

**类型:** `string | null`  
**默认:** `null`  
**说明:** 自定义模型 API Key

⚠️ **安全提示:** 建议使用环境变量 `CODY_MODEL_API_KEY`，不要写入配置文件。

```json
{
  "model_api_key": "sk-..."
}
```

---

#### `claude_oauth_token`

**类型:** `string | null`  
**默认:** `null`  
**说明:** Claude OAuth Token（来自 `claude login`）

```json
{
  "claude_oauth_token": "your-oauth-token"
}
```

---

#### `coding_plan_key`

**类型:** `string | null`  
**默认:** `null`  
**说明:** 阿里云百炼 Coding Plan Key (`sk-sp-xxx`)

```json
{
  "coding_plan_key": "sk-sp-..."
}
```

---

#### `coding_plan_protocol`

**类型:** `"openai" | "anthropic"`  
**默认:** `"openai"`  
**说明:** Coding Plan 使用的协议

```json
{
  "coding_plan_key": "sk-sp-...",
  "coding_plan_protocol": "anthropic"
}
```

**协议说明：**
- `openai` — OpenAI 兼容协议（默认）
- `anthropic` — Anthropic 兼容协议

---

#### `enable_thinking`

**类型:** `boolean`  
**默认:** `false`  
**说明:** 启用思考模式（显示模型推理过程）

```json
{
  "enable_thinking": true
}
```

---

#### `thinking_budget`

**类型:** `integer | null`  
**默认:** `null`  
**说明:** 思考模式最大 token 数

```json
{
  "enable_thinking": true,
  "thinking_budget": 10000
}
```

---

### 认证配置 (`auth`)

#### `auth.type`

**类型:** `"api_key" | "oauth"`  
**默认:** `"api_key"`  
**说明:** 认证类型

```json
{
  "auth": {
    "type": "api_key"
  }
}
```

---

#### `auth.api_key`

**类型:** `string | null`  
**默认:** `null`  
**说明:** API Key（用于 Server 认证）

⚠️ **安全提示:** 建议使用环境变量。

---

#### `auth.token`

**类型:** `string | null`  
**默认:** `null`  
**说明:** OAuth Token

---

#### `auth.refresh_token`

**类型:** `string | null`  
**默认:** `null`  
**说明:** OAuth 刷新 Token

---

#### `auth.expires_at`

**类型:** `string | null`  
**默认:** `null`  
**说明:** Token 过期时间（ISO 8601）

---

### 技能配置 (`skills`)

#### `skills.enabled`

**类型:** `string[]`  
**默认:** `[]`  
**说明:** 启用的技能列表（空表示全部启用）

```json
{
  "skills": {
    "enabled": ["git", "github", "python"]
  }
}
```

---

#### `skills.disabled`

**类型:** `string[]`  
**默认:** `[]`  
**说明:** 禁用的技能列表

```json
{
  "skills": {
    "disabled": ["docker", "java"]
  }
}
```

**优先级规则：**
1. `disabled` 中的技能始终禁用
2. 如果 `enabled` 非空，只启用列表中的技能
3. 如果 `enabled` 为空，默认启用所有技能

---

### MCP 配置 (`mcp`)

#### `mcp.servers`

**类型:** `McpServerConfig[]`  
**默认:** `[]`  
**说明:** MCP 服务器列表

```json
{
  "mcp": {
    "servers": [
      {
        "name": "github",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {
          "GITHUB_TOKEN": "..."
        }
      },
      {
        "name": "filesystem",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem"],
        "env": {}
      }
    ]
  }
}
```

**McpServerConfig 字段：**
| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 服务器名称 |
| `command` | string | 启动命令 |
| `args` | string[] | 命令参数 |
| `env` | object | 环境变量 |

---

### 权限配置 (`permissions`)

#### `permissions.overrides`

**类型:** `object`  
**默认:** `{}`  
**说明:** 工具级权限覆盖

```json
{
  "permissions": {
    "overrides": {
      "exec_command": "allow",
      "write_file": "confirm"
    }
  }
}
```

**权限级别：**
- `allow` — 始终允许
- `deny` — 始终拒绝
- `confirm` — 需要确认（默认）

---

#### `permissions.default_level`

**类型:** `"allow" | "deny" | "confirm"`  
**默认:** `"confirm"`  
**说明:** 未配置工具的默认权限

```json
{
  "permissions": {
    "default_level": "confirm"
  }
}
```

---

### 安全配置 (`security`)

#### `security.allowed_commands`

**类型:** `string[] | null`  
**默认:** `null`  
**说明:** 允许执行的命令白名单（null 表示不限制）

```json
{
  "security": {
    "allowed_commands": ["ls", "cat", "grep", "python3", "npm", "git"]
  }
}
```

---

#### `security.restricted_paths`

**类型:** `string[]`  
**默认:** `[]`  
**说明:** 限制访问的路径列表

```json
{
  "security": {
    "restricted_paths": ["/etc", "/root", "/var"]
  }
}
```

---

#### `security.require_confirmation`

**类型:** `boolean`  
**默认:** `true`  
**说明:** 是否需要确认危险操作

```json
{
  "security": {
    "require_confirmation": true
  }
}
```

---

### 速率限制配置 (`rate_limit`)

用于 RPC Server 的限流。

#### `rate_limit.enabled`

**类型:** `boolean`  
**默认:** `false`  
**说明:** 是否启用限流

```json
{
  "rate_limit": {
    "enabled": true
  }
}
```

---

#### `rate_limit.max_requests`

**类型:** `integer`  
**默认:** `60`  
**说明:** 窗口内最大请求数

```json
{
  "rate_limit": {
    "max_requests": 100
  }
}
```

---

#### `rate_limit.window_seconds`

**类型:** `number`  
**默认:** `60.0`  
**说明:** 时间窗口（秒）

```json
{
  "rate_limit": {
    "window_seconds": 60.0
  }
}
```

**示例：** 60 秒内最多 60 个请求

---

## 环境变量

所有配置项都可以通过环境变量覆盖：

| 环境变量 | 配置项 | 示例 |
|---------|--------|------|
| `CODY_MODEL` | `model` | `glm-4` |
| `CODY_MODEL_BASE_URL` | `model_base_url` | `https://...` |
| `CODY_MODEL_API_KEY` | `model_api_key` | `sk-...` |
| `CLAUDE_OAUTH_TOKEN` | `claude_oauth_token` | `...` |
| `CODY_CODING_PLAN_KEY` | `coding_plan_key` | `sk-sp-...` |
| `CODY_CODING_PLAN_PROTOCOL` | `coding_plan_protocol` | `anthropic` |
| `CODY_ENABLE_THINKING` | `enable_thinking` | `true` |
| `CODY_THINKING_BUDGET` | `thinking_budget` | `10000` |
| `ANTHROPIC_API_KEY` | (自动使用) | `sk-ant-...` |

**优先级：** 环境变量 > 配置文件 > 默认值

---

## 配置管理命令

### 查看配置

```bash
cody config show
```

**输出示例：**
```json
{
  "model": "anthropic:claude-sonnet-4-0",
  "model_base_url": null,
  "enable_thinking": false,
  "skills": {
    "enabled": ["git", "github"],
    "disabled": []
  },
  ...
}
```

---

### 设置配置

```bash
# 设置模型
cody config set model "anthropic:claude-sonnet-4-0"

# 设置 API 地址
cody config set model_base_url "https://..."

# 设置 API Key（不推荐）
cody config set model_api_key "sk-..."
```

⚠️ **提示:** API Key 建议使用环境变量。

---

## 配置示例

### 示例 1：基础配置（Anthropic）

```json
{
  "model": "anthropic:claude-sonnet-4-0",
  "skills": {
    "enabled": ["git", "github", "python"]
  }
}
```

---

### 示例 2：使用智谱 GLM

```json
{
  "model": "glm-4",
  "model_base_url": "https://open.bigmodel.cn/api/paas/v4/",
  "skills": {
    "enabled": ["git", "python"]
  }
}
```

配合环境变量：
```bash
export CODY_MODEL_API_KEY='sk-...'
```

---

### 示例 3：阿里云百炼 Coding Plan

```json
{
  "model": "qwen3.5",
  "coding_plan_protocol": "openai",
  "enable_thinking": true,
  "thinking_budget": 10000
}
```

配合环境变量：
```bash
export CODY_CODING_PLAN_KEY='sk-sp-...'
```

---

### 示例 4：启用 MCP 服务器

```json
{
  "model": "anthropic:claude-sonnet-4-0",
  "mcp": {
    "servers": [
      {
        "name": "github",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {
          "GITHUB_TOKEN": "ghp_..."
        }
      }
    ]
  }
}
```

---

### 示例 5：Server 安全配置

```json
{
  "auth": {
    "type": "api_key",
    "api_key": "cody_..."
  },
  "rate_limit": {
    "enabled": true,
    "max_requests": 60,
    "window_seconds": 60.0
  },
  "security": {
    "allowed_commands": ["ls", "cat", "grep", "python3", "git"],
    "restricted_paths": ["/etc", "/root"],
    "require_confirmation": true
  }
}
```

---

## 初始化配置

```bash
# 在项目目录初始化
cody init

# 创建的文件：
# .cody/
# ├── config.json    # 项目配置
# └── skills/        # 项目技能目录
```

---

## 最佳实践

### 1. 使用环境变量管理敏感信息

```bash
# .env 文件（不提交到 Git）
CODY_MODEL_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
CODY_CODING_PLAN_KEY=sk-sp-...
```

```bash
# 加载环境变量
source .env
```

---

### 2. 项目配置与全局配置分离

```bash
# 全局配置（~/.cody/config.json）
{
  "model": "anthropic:claude-sonnet-4-0",
  "skills": {
    "enabled": ["git", "github"]
  }
}

# 项目配置（.cody/config.json）
{
  "model": "glm-4",
  "model_base_url": "https://...",
  "skills": {
    "enabled": ["python", "testing"]
  }
}
```

---

### 3. 使用 CLI 参数临时覆盖

```bash
# 临时使用不同模型
cody run --model glm-4 "任务"

# 临时启用思考
cody run --thinking "复杂任务"

# 临时指定工作目录
cody run --workdir /path/to/project "任务"
```

---

### 4. 定期审计配置

```bash
# 查看当前配置
cody config show

# 检查技能配置
cody skills list

# 查看审计日志
# ~/.cody/audit.db
```

---

## 故障排查

### Q: 配置不生效？

检查配置优先级：
```bash
# 1. 查看项目配置
cat .cody/config.json

# 2. 查看全局配置
cat ~/.cody/config.json

# 3. 检查环境变量
env | grep CODY

# 4. 查看生效配置
cody config show
```

---

### Q: API Key 错误？

确保 Key 正确：
```bash
# 检查环境变量
echo $ANTHROPIC_API_KEY
echo $CODY_MODEL_API_KEY

# 测试连接
cody run "hello"
```

---

### Q: 技能未加载？

```bash
# 列出技能
cody skills list

# 查看技能文档
cody skills show <skill-name>

# 检查技能目录
ls -la .cody/skills/
ls -la ~/.cody/skills/
```

---

**最后更新:** 2026-02-28
