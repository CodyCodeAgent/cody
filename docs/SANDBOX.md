# Cody Sandbox 指南

Cody 通过统一的 `SandboxBackend → SandboxHandle` 边界执行所有 guest 进程。Command
工具、Quality Gate、stdio MCP、LSP 和子 Agent 命令不能绕过该边界。Sandbox 生命周期
属于 canonical Run，可随 checkpoint snapshot、暂停、恢复、fork 和终止。

## 1. 快速启用

```json
{
  "sandbox": {
    "enabled": true,
    "backend": "auto",
    "fail_if_unavailable": true,
    "private_workspace": false,
    "network_mode": "disabled",
    "allowed_domains": [],
    "allowed_cidrs": [],
    "denied_roots": ["~/.ssh", "~/.aws"],
    "cpu_count": 2,
    "memory_mb": 2048,
    "process_limit": 128,
    "timeout_seconds": 300,
    "env": {
      "GOCACHE": "/workspace/.cache/go-build"
    }
  }
}
```

环境变量快捷覆盖：

```bash
export CODY_SANDBOX_ENABLED=true
export CODY_SANDBOX_BACKEND=auto
export CODY_SANDBOX_IMAGE=ubuntu:24.04
```

`enabled=false` 时使用 `local-policy` 兼容后端，网络保持 unrestricted。它保留路径、
命令、超时和环境清理逻辑，但不是 OS 级安全边界。

## 2. 后端选择

| 后端 | 平台/依赖 | 隔离能力 | 典型用途 |
|------|-----------|----------|----------|
| `auto` | macOS 选择 Seatbelt；Linux 选择 Bubblewrap | 与被选后端相同 | 本地开发默认 |
| `seatbelt` | macOS `sandbox-exec` | 文件、进程和 socket policy | macOS 本地隔离 |
| `bubblewrap` / `bwrap` | Linux 安装 `bwrap` | mount namespace、只读系统、网络 namespace | Linux 本地/CI |
| `docker` | Docker daemon/CLI | 容器、mount、网络和资源限制 | 服务部署 |
| `podman` | Podman CLI | rootless/container 隔离 | Linux 服务部署 |
| `remote` | 注册 `RemoteSandboxBackend` | 由远程 provider 保证 | microVM/Kubernetes/托管 Sandbox |
| `local-policy` | 无额外依赖 | 无内核隔离 | 明确信任本机代码时兼容使用 |

`fail_if_unavailable=true` 会 fail closed。只有明确接受无内核隔离时，才设置为 `false`
允许回退到 `local-policy`。

## 3. 文件系统策略

`workdir` 和 `security.allowed_roots` 同时成为 guest 的 read/write roots；
`sandbox.denied_roots` 始终优先拒绝。`private_workspace=true` 要求后端提供 Run 私有工作区，
避免并行 Run 直接共享修改。

```json
{
  "security": {
    "allowed_roots": ["/workspace/shared"],
    "strict_read_boundary": true
  },
  "sandbox": {
    "enabled": true,
    "denied_roots": ["~/.ssh", "~/.aws", "~/.kube"],
    "private_workspace": true
  }
}
```

注意：`security.strict_read_boundary` 管理 Cody 文件工具；Sandbox filesystem policy
管理 guest 进程。生产环境应同时配置两者。

## 4. 网络策略

支持四种模式：

- `disabled`：禁止 guest 网络。
- `allowlist`：只允许 `allowed_domains`/`allowed_cidrs`；域名通常需要 policy proxy。
- `proxied`：所有流量经 `proxy_url`。
- `unrestricted`：允许直接网络访问，只适用于可信任务。

Seatbelt 和容器内核只能稳定约束 socket/IP，不能安全地把 DNS 名长期映射为固定 IP。
因此 hostname allowlist 必须配套代理：

- Seatbelt 要求 `proxy_url` 使用 `unix://` 代理 socket。
- Docker/Podman 还要求管理员预先创建仅连接代理的 `network_name`，阻止 guest 绕过代理
  直连公网。
- HTTP MCP URL 会在宿主侧按同一 Run network policy 检查。

```json
{
  "sandbox": {
    "enabled": true,
    "backend": "docker",
    "image": "cody-sandbox:stable",
    "network_mode": "proxied",
    "proxy_url": "http://sandbox-proxy:3128",
    "network_name": "cody-proxy-only"
  }
}
```

## 5. 环境变量与秘密

宿主环境不会被隐式继承。只有 `sandbox.env` 和单次执行请求明确给出的变量进入 guest。
模型 API Key、云凭证和登录 token 应保留在可信宿主，不要复制到 Sandbox。

`sandbox.env` 适合非敏感构建配置，例如 cache 路径、locale 或工具开关。若 guest 必须
访问短期凭证，应由外部 secret broker 发放最小权限、短有效期凭证，并确保事件和日志
不会记录明文。

## 6. 资源限制

| 字段 | 说明 |
|------|------|
| `cpu_count` | 容器/远程后端 CPU quota |
| `memory_mb` | 内存上限 |
| `process_limit` | PID/process 上限 |
| `timeout_seconds` | guest 命令默认超时；未设置时使用 `security.command_timeout` |
| `image_pull_policy` | `never`、`if_missing` 或 `always` |
| `state_root` | 本地 snapshot/private workspace 状态目录 |

Seatbelt/Bubblewrap 能力受宿主 OS 限制，不保证所有 quota 都可用；需要硬资源配额时使用
容器、microVM 或远程 provider。

## 7. 生命周期与恢复

```text
create → start → exec/spawn
               ↘ snapshot → pause/wait
snapshot reference → checkpoint/artifact → restore → resume
                                              ↘ fork
terminal state → terminate
```

Sandbox 的 create/start/snapshot/pause/resume/failure/terminate 都会产生 `RunEvent`。
等待人工审批时，Runtime 保存 `SANDBOX_SNAPSHOT` Artifact 并释放 worker；新进程恢复 Run
时，从 checkpoint 引用恢复相同执行状态。

后端必须保证：

1. `exec` 使用 argv，不把不可信参数重新拼接为 shell 字符串。
2. snapshot reference 在服务重启后仍可访问。
3. restore/fork 不共享可变私有目录。
4. terminate 幂等，失败后不会遗留可访问的 Run 环境。
5. 超时和取消能终止整个 guest process tree。

## 8. 远程 Sandbox

实现 `RemoteSandboxTransport` 并注册：

```python
from cody.core.sandbox import RemoteSandboxBackend, SandboxManager

manager = SandboxManager()
manager.register(RemoteSandboxBackend(transport, name="remote"))

runtime = CodyRuntime.from_config(
    config,
    workdir,
    sandbox_manager=manager,
)
```

Transport 负责远端 create、exec、spawn、pause、resume、snapshot、restore、fork 和
terminate。认证、租户隔离、镜像供应链、日志保留和 egress policy 由 provider adapter
及部署平台负责。

## 9. 信任边界

Sandboxed guest：

- `exec_command` 及其他命令工具；
- Quality Gate 命令；
- stdio MCP server；
- LSP server；
- 子 Agent 发起的命令。

Trusted host：

- 模型 API client；
- Python hook 和自定义工具函数本身；
- workflow node/condition handler；
- model/store/auth/presentation extension；
- HTTP MCP client（URL 仍受 network policy 检查）。

安装的 Python 扩展等同应用代码，不能视为被 Sandbox 隔离的第三方脚本。

## 10. 上线检查清单

- `fail_if_unavailable=true`，启动时验证实际选中的 backend。
- 默认 `network_mode=disabled`；按域名放行时配置不可绕过的代理网络。
- `workdir`、allowed roots、denied roots 与多租户边界一致。
- guest 不继承宿主 secrets，镜像中也不包含长期凭证。
- Docker/Podman 使用固定 digest 或受控镜像仓库，并配置资源上限。
- snapshot/object storage 启用加密、生命周期和租户前缀。
- 对 pause/resume、进程崩溃恢复、timeout、取消和 process-tree 清理做部署级演练。
- 审计记录能通过 `run_id` 关联 actor、命令、审批、checkpoint 和 artifact。

## 11. 故障排查

| 现象 | 检查 |
|------|------|
| `auto` 启动失败 | macOS 检查 `sandbox-exec`；Linux 检查 `bwrap`；确认 fail-closed 策略 |
| guest 无法写文件 | workdir/allowed roots、denied roots、private workspace mount |
| allowlist 无法联网 | policy proxy、`proxy_url`、容器 `network_name` 和 DNS 配置 |
| LSP/MCP 启动失败 | server binary 是否在 guest PATH；所需 cache/env 是否显式传入 |
| resume 找不到 snapshot | state/object storage 是否持久化；远程 reference 是否过期 |
| 宿主命令仍被执行 | 确认 Run 绑定的 `SandboxHandle`，不要在自定义 Python handler 中直接 subprocess |

**最后更新：2026-07-12**
