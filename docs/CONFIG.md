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

## CODY.md 项目说明文件

除 JSON 配置外，Cody 还支持 `CODY.md` 项目说明文件，在每次 session 启动时自动读取并注入系统提示：

| 文件路径 | 说明 |
|----------|------|
| `~/.cody/CODY.md` | 全局用户级说明，对所有项目生效 |
| `<workdir>/CODY.md` | 项目级说明，仅对当前项目生效 |

两个文件均可选，均存在时按"全局 + 分隔符 + 项目"的顺序合并。

生成模板：`cody init`（在项目根目录创建 `CODY.md` 模板）。

详见 [CLI 文档 — CODY.md 说明](CLI.md#codymd-项目说明文件)。

---

## 配置文件结构

```json
{
  "model": "claude-sonnet-4-0",
  "model_base_url": null,
  "model_api_key": null,
  "enable_thinking": false,
  "thinking_budget": null,
  "auth": {
    "type": "api_key",
    "api_key": null
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
    "allowed_roots": [],
    "strict_read_boundary": false,
    "require_confirmation": true
  },
  "rate_limit": {
    "enabled": false,
    "max_requests": 60,
    "window_seconds": 60.0
  },
  "retry": {
    "enabled": true,
    "max_retries": 3,
    "base_delay": 2.0,
    "max_delay": 30.0
  },
  "compaction": {
    "use_llm": false,
    "model": null,
    "model_base_url": null,
    "max_tokens": 100000,
    "trigger_ratio": 0.0,
    "context_window_tokens": 0,
    "keep_recent": 4,
    "keep_recent_tokens": 0,
    "max_summary_tokens": 500,
    "enable_pruning": true,
    "prune_protect_tokens": 40000,
    "prune_min_saving_tokens": 20000,
    "prune_min_content_tokens": 200
  }
}
```

---

## 配置项详解

### 模型配置

#### `model`

**类型:** `string`  
**默认:** `"claude-sonnet-4-0"`  
**说明:** AI 模型名称

```json
{
  "model": "claude-sonnet-4-0"
}
```

**支持的模型：**
- `claude-sonnet-4-0`
- `claude-opus-4-0`
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
**说明:** 模型 API Key。OpenAI 兼容提供商的 API Key。

`cody config setup` 交互式设置后会自动保存到配置文件。也可通过环境变量 `CODY_MODEL_API_KEY` 覆盖。

```json
{
  "model_api_key": "sk-..."
}
```

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

用于 Web Backend（HTTP API）的访问控制。

#### `auth.type`

**类型:** `"api_key"`
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
**说明:** API Key（用于 HTTP API 认证）

⚠️ **安全提示:** 建议使用环境变量。

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

**stdio 传输（子进程，默认）：**

```json
{
  "mcp": {
    "servers": [
      {
        "name": "github",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {
          "GITHUB_TOKEN": "..."
        }
      }
    ]
  }
}
```

**HTTP 传输（远程端点，v1.9.0+）：**

```json
{
  "mcp": {
    "servers": [
      {
        "name": "feishu",
        "transport": "http",
        "url": "https://mcp.feishu.cn/mcp",
        "headers": {
          "X-Lark-MCP-UAT": "your-token"
        }
      }
    ]
  }
}
```

**McpServerConfig 字段：**

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `name` | string | — | 服务器名称（必填） |
| `transport` | `"stdio"` 或 `"http"` | `"stdio"` | 传输方式 |
| `command` | string | `""` | 启动命令（stdio） |
| `args` | string[] | `[]` | 命令参数（stdio） |
| `env` | object | `{}` | 环境变量（stdio） |
| `url` | string | `""` | HTTP 端点 URL（http） |
| `headers` | object | `{}` | HTTP 请求头（http） |

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
**说明:** 允许执行的命令白名单（null 表示不限制）。当设置后，管道和链式命令中的每个命令都会逐一检查白名单。

```json
{
  "security": {
    "allowed_commands": ["ls", "cat", "grep", "python3", "npm", "git"]
  }
}
```

---

#### `security.blocked_commands`

**类型:** `string[]`
**默认:** `[]`
**说明:** 用户自定义的危险命令模式黑名单。框架内置拦截 `rm -rf /`、`dd if=`、`:(){` 等极端破坏性模式，此字段供 SDK 用户按需扩展。

> **设计原则：** 框架提供机制，不提供策略。Cody 不会默认禁用 `curl`、`python` 等常用命令，用户可根据实际场景配置。

```json
{
  "security": {
    "blocked_commands": ["rm -rf", "mkfs", "shutdown", "reboot"]
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

#### `security.allowed_roots`

**类型:** `string[]`
**默认:** `[]`
**说明:** 允许工具读写的额外目录列表（访问边界）。

`workdir` 始终隐式允许，无需重复添加。列表为空时，工具只能访问 `workdir`。
**仅支持绝对路径**，相对路径会在启动时抛出错误。

```json
{
  "security": {
    "allowed_roots": ["/data/shared", "/shared/libs"]
  }
}
```

**典型用例：**
- Monorepo：`workdir` 为某子包，但需要访问根目录的共享库
- AI 需要读写特定数据目录但不应访问整个系统

也可通过 CLI 的 `--allow-root` 或 Server 请求的 `allowed_roots` 字段在运行时追加（不覆盖此配置）。

---

#### `security.strict_read_boundary`

**类型:** `boolean`
**默认:** `false`
**说明:** 是否限制读操作的访问边界。

默认情况下，读操作（`read_file`、`grep`、`glob`、`list_directory`、`search_files`）可以访问 `workdir` 和 `allowed_roots` 之外的路径。设为 `true` 后，读操作也受 `workdir` + `allowed_roots` 边界限制，越界会被拒绝。

写操作始终受限，不受此配置影响。

```json
{
  "security": {
    "strict_read_boundary": true,
    "allowed_roots": ["/data/shared"]
  }
}
```

**典型用例：**

- 多租户部署：防止 Agent 读取其他用户的文件
- 安全敏感环境：严格控制 Agent 的可见范围

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

用于 Web Backend（HTTP API）的限流。

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

### LLM 重试配置 (`retry`)

LLM API 调用的自动重试。对 429（rate limit）和 5xx（服务端错误）使用指数退避重试。对客户端错误（auth、context overflow）不重试。

#### `retry.enabled`

**类型:** `boolean`
**默认:** `true`
**说明:** 是否启用 LLM API 自动重试

---

#### `retry.max_retries`

**类型:** `integer`
**默认:** `3`
**说明:** 最大重试次数（不含首次调用）

---

#### `retry.base_delay`

**类型:** `number`
**默认:** `2.0`
**说明:** 首次重试延迟（秒）。后续按指数增长：2s → 4s → 8s

---

#### `retry.max_delay`

**类型:** `number`
**默认:** `30.0`
**说明:** 最大重试延迟（秒）

---

**示例：** 自定义重试策略

```json
{
  "retry": {
    "enabled": true,
    "max_retries": 5,
    "base_delay": 1.0,
    "max_delay": 60.0
  }
}
```

> **注意：** 重试覆盖 `run()` 和 `run_sync()`。`run_stream()` 的流式调用暂不支持自动重试。

---

### 上下文压缩配置 (`compaction`)

控制对话历史自动压缩行为。当消息总 token 数超过阈值时，自动将旧消息压缩为摘要。

#### `compaction.use_llm`

**类型:** `boolean`
**默认:** `false`
**说明:** 是否启用 LLM 语义摘要。关闭时使用截断式压缩（每条消息截取前 200 字符）

```json
{
  "compaction": {
    "use_llm": true
  }
}
```

---

#### `compaction.model`

**类型:** `string | null`
**默认:** `null`（沿用主 `model` 配置）
**说明:** 用于生成摘要的模型名称。建议使用低成本模型（如 `gpt-4o-mini`）

---

#### `compaction.model_base_url`

**类型:** `string | null`
**默认:** `null`（沿用主 `model_base_url` 配置）
**说明:** 摘要模型的 API 地址。允许将摘要请求发送到独立的模型服务

---

#### `compaction.max_tokens`

**类型:** `integer`
**默认:** `100000`
**说明:** 触发压缩的 token 阈值。当消息总 token 数超过此值时开始压缩。如果同时设置了 `trigger_ratio` 和 `context_window_tokens`，此值会被覆盖

---

#### `compaction.trigger_ratio`

**类型:** `float`
**默认:** `0.0`（禁用）
**说明:** 按模型上下文窗口百分比触发压缩。设为 `0.75` 表示在 75% 容量时触发。需同时设置 `context_window_tokens`

---

#### `compaction.context_window_tokens`

**类型:** `integer`
**默认:** `0`
**说明:** 模型的上下文窗口大小（token 数）。与 `trigger_ratio` 配合使用。例如 GPT-4 设为 `128000`

---

#### `compaction.keep_recent`

**类型:** `integer`
**默认:** `4`
**说明:** 压缩时保留的最近消息数（按条数）。当 `keep_recent_tokens > 0` 时，此值被覆盖

---

#### `compaction.keep_recent_tokens`

**类型:** `integer`
**默认:** `0`（禁用，使用 `keep_recent` 按条数）
**说明:** 压缩时保留最近消息的 token 预算。设为如 `20000` 表示保留最近约 20k token 的消息。比按固定条数更精确

---

#### `compaction.max_summary_tokens`

**类型:** `integer`
**默认:** `500`
**说明:** LLM 生成摘要的最大 token 数

---

#### `compaction.enable_pruning`

**类型:** `boolean`
**默认:** `true`
**说明:** 启用选择性修剪（Selective Pruning）。在执行全量压缩前，先尝试将旧的大型工具输出替换为轻量标记。灵感来自 OpenCode 的两阶段策略，能在不丢失对话结构的情况下释放 token 空间

---

#### `compaction.prune_protect_tokens`

**类型:** `integer`
**默认:** `40000`
**说明:** 最近消息的保护窗口（token 数）。在此窗口内的消息永远不会被修剪

---

#### `compaction.prune_min_saving_tokens`

**类型:** `integer`
**默认:** `20000`
**说明:** 执行修剪的最低节省阈值。只有当可释放的 token 数超过此值时才执行修剪

---

#### `compaction.prune_min_content_tokens`

**类型:** `integer`
**默认:** `200`
**说明:** 单条消息的最小修剪阈值。低于此 token 数的消息不会被修剪（避免修剪小输出）

---

**完整示例：** 按 128k 窗口 75% 触发 + token-based 保留 + LLM 摘要 + 修剪

```json
{
  "compaction": {
    "use_llm": true,
    "model": "gpt-4o-mini",
    "model_base_url": "https://api.openai.com/v1",
    "trigger_ratio": 0.75,
    "context_window_tokens": 128000,
    "keep_recent_tokens": 20000,
    "max_summary_tokens": 600,
    "enable_pruning": true,
    "prune_protect_tokens": 40000,
    "prune_min_saving_tokens": 20000,
    "prune_min_content_tokens": 200
  }
}
```

> 上例中 `trigger_ratio=0.75 × context_window_tokens=128000 = 96000`，当 token 超 96k 时触发。
> `keep_recent_tokens=20000` 保留最近约 20k token 的消息（代替固定 4 条）。

> **注意：** `run_sync()` 同步模式下 LLM 压缩不可用，会自动降级为截断式压缩。
> 修剪（Pruning）在同步和异步模式下均可用。

---

## 环境变量

所有配置项都可以通过环境变量覆盖：

| 环境变量 | 配置项 | 示例 |
|---------|--------|------|
| `CODY_MODEL` | `model` | `glm-4` |
| `CODY_MODEL_BASE_URL` | `model_base_url` | `https://...` |
| `CODY_MODEL_API_KEY` | `model_api_key` | `sk-...` |
| `CODY_CODING_PLAN_KEY` | `model_api_key`（兼容旧配置） | `sk-sp-...` |
| `CODY_ENABLE_THINKING` | `enable_thinking` | `true` |
| `CODY_THINKING_BUDGET` | `thinking_budget` | `10000` |
| `CODY_COMPACTION_USE_LLM` | `compaction.use_llm` | `true` |
| `CODY_COMPACTION_MODEL` | `compaction.model` | `gpt-4o-mini` |
| `CODY_CORS_ORIGINS` | Web CORS 允许的源（逗号分隔） | `http://localhost:5173,http://localhost:3000` |

**优先级：** 环境变量 > 配置文件 > 默认值

> **`CODY_CORS_ORIGINS`** 仅影响 Web Backend。未设置时默认允许 `localhost:5173`、`localhost:3000`（及对应 127.0.0.1）。生产部署时设置为实际域名：
> ```bash
> export CODY_CORS_ORIGINS="https://cody.example.com,https://app.example.com"
> ```

---

## 配置管理命令

### 交互式配置（推荐）

```bash
cody config setup
```

交互式引导配置模型提供商、API Key 等信息，保存到 `~/.cody/config.json`。

首次使用 `cody run`/`chat`/`tui` 时如果未配置 API Key，也会自动触发。

---

### 查看配置

```bash
cody config show
```

**输出示例：**
```json
{
  "model": "claude-sonnet-4-0",
  "model_api_key": "sk-ant...xyz",
  "enable_thinking": false,
  "skills": {
    "enabled": ["git", "github"],
    "disabled": []
  },
  ...
}
```

> API Key 在显示时会自动脱敏。

---

### 设置配置

```bash
# 设置模型
cody config set model "claude-sonnet-4-0"

# 设置 API 地址
cody config set model_base_url "https://..."

# 设置 API Key
cody config set model_api_key "sk-..."

# 启用思考模式
cody config set enable_thinking true
cody config set thinking_budget 10000
```

---

## 配置示例

### 示例 1：基础配置

```json
{
  "model": "claude-sonnet-4-0",
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
  "model_api_key": "sk-...",
  "skills": {
    "enabled": ["git", "python"]
  }
}
```

---

### 示例 3：阿里云百炼（Qwen）

```json
{
  "model": "qwen3.5",
  "model_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "model_api_key": "sk-...",
  "enable_thinking": true,
  "thinking_budget": 10000
}
```

---

### 示例 4：启用 MCP 服务器

```json
{
  "model": "claude-sonnet-4-0",
  "mcp": {
    "servers": [
      {
        "name": "github",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {
          "GITHUB_TOKEN": "ghp_..."
        }
      },
      {
        "name": "feishu",
        "transport": "http",
        "url": "https://mcp.feishu.cn/mcp",
        "headers": {
          "X-Lark-MCP-UAT": "your-token"
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

## 安装依赖分层

`pip install cody-ai` 仅安装核心 SDK（4 个依赖），CLI/TUI/Web 需通过可选依赖组安装：

| 安装方式 | 说明 |
|----------|------|
| `pip install cody-ai` | 核心 SDK（pydantic-ai、pydantic、httpx） |
| `pip install cody-ai[cli]` | + CLI（click、rich） |
| `pip install cody-ai[tui]` | + TUI（textual） |
| `pip install cody-ai[web]` | + Web（fastapi、uvicorn） |
| `pip install cody-ai[all]` | 全部功能 |
| `pip install cody-ai[dev]` | 全部 + 开发工具（pytest、ruff 等） |

缺少可选依赖时，入口模块会提示安装命令（如 `pip install cody-ai[cli]`）。

---

## 最佳实践

### 1. 使用 `cody config setup` 管理 API Key

```bash
# 交互式配置，API Key 安全保存到 ~/.cody/config.json
cody config setup
```

也可通过环境变量覆盖（优先级高于配置文件）：

```bash
export CODY_MODEL_API_KEY=sk-...
```

---

### 2. 项目配置与全局配置分离

```bash
# 全局配置（~/.cody/config.json）
{
  "model": "claude-sonnet-4-0",
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
echo $CODY_MODEL_API_KEY

# 或查看配置
cody config show

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

### Q: 如何查看运行日志？

Cody 自动将日志写入 `~/.cody/logs/cody.log`（自动轮转，5 MB / 3 备份）：

```bash
# 查看最近日志
tail -50 ~/.cody/logs/cody.log

# 实时跟踪
tail -f ~/.cody/logs/cody.log

# 启用详细日志（同时输出到终端）
cody run -v "your prompt"
```

日志目录结构：
```
~/.cody/logs/
├── cody.log          # 当前日志
├── cody.log.1        # 第 1 个备份
├── cody.log.2        # 第 2 个备份
└── cody.log.3        # 第 3 个备份
```

---

**最后更新:** 2026-03-07
