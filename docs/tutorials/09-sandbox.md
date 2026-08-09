# 09 · 在 Sandbox 中执行

<div class="tutorial-outcome"><strong>完成后：</strong>你会选择合适的后端，默认禁网、限制文件与资源，并验证执行没有悄悄回退到宿主。</div>

## 1. 选择后端

| 环境 | 建议后端 | 说明 |
|---|---|---|
| macOS 本地 | `seatbelt` 或 `auto` | 使用系统 `sandbox-exec` |
| Linux 本地/CI | `bubblewrap` 或 `auto` | 依赖 `bwrap` 与 namespace 能力 |
| 服务部署 | `docker` / `podman` | 支持镜像、网络与资源 quota |
| 外部隔离平台 | `remote` | 需要你实现 transport；Cody 不托管服务 |
| 完全可信任务 | `local-policy` | 只有策略检查，不是内核隔离 |

## 2. 创建 fail-closed 配置

`.cody/config.json`：

```json
{
  "security": {
    "strict_read_boundary": true,
    "allowed_roots": []
  },
  "sandbox": {
    "enabled": true,
    "backend": "auto",
    "fail_if_unavailable": true,
    "private_workspace": false,
    "network_mode": "disabled",
    "denied_roots": ["~/.ssh", "~/.aws", "~/.kube"],
    "cpu_count": 2,
    "memory_mb": 2048,
    "process_limit": 128,
    "timeout_seconds": 300,
    "env": {
      "LANG": "C.UTF-8"
    }
  }
}
```

`fail_if_unavailable=true` 很关键：Bubblewrap 或容器后端不可用时直接失败，不得静默降级成 `local-policy`。

## 3. 运行边界测试

```bash
cody run --workdir /tmp/cody-tutorial \
  "创建 sandbox-proof.txt；尝试读取 ~/.ssh；尝试访问外网；报告每一步真实结果"
```

至少验证：

- 工作目录能按策略读写。
- denied root 无法读取。
- `network_mode=disabled` 时 guest 无法联网。
- 超时能终止整个 process tree。
- guest 看不到宿主的模型 API Key 与云凭证。
- Runtime event 显示实际选中的 sandbox backend。

## 4. 容器部署补充

```json
{
  "sandbox": {
    "enabled": true,
    "backend": "docker",
    "image": "registry.example.com/cody-sandbox@sha256:...",
    "image_pull_policy": "never",
    "network_mode": "disabled",
    "private_workspace": true
  }
}
```

固定镜像 digest，使用只读根文件系统和受限 `/tmp`，限制 CPU、内存与 PID。若需域名 allowlist，应通过不可绕过的代理网络，而不是依赖易变化的 DNS→IP 映射。

## 5. 理解信任边界

命令工具、Quality Gate、stdio MCP、LSP 和子 Agent 命令属于 guest。模型 API client、自定义 Python hook/node/extension 属于可信宿主。安装一个 Python 扩展等同于执行应用代码，不能被 guest Sandbox 保护。

[完整后端和网络策略](../SANDBOX.md)
