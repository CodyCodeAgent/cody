# 11 · CLI、TUI 与 Web 协作

<div class="tutorial-outcome"><strong>完成后：</strong>你会从一个入口启动 Run，在另一个入口观察、审批或恢复，并确认四个产品表面共享状态。</div>

## 1. 安装所有本地入口

```bash
pip install 'cody-ai[all]'
```

| 入口 | 适用场景 | 命令/API |
|---|---|---|
| Python SDK | 嵌入 Python 应用 | `AsyncCodyClient` / `CodyRuntime` |
| CLI | 脚本、CI、运维控制 | `cody ...` |
| TUI | 全屏终端交互 | `cody tui` |
| Web | 浏览器与非 Python 客户端 | `cody-web run` |

## 2. 从 CLI 启动并记录 run_id

```bash
cody run --workdir /tmp/cody-tutorial "分析项目并生成测试计划"
cody runs list --workdir /tmp/cody-tutorial
```

## 3. 启动 Web

```bash
export CODY_AUTH_API_KEY='use-a-secret-manager-in-production'
cody-web run --port 8000
```

打开 `http://localhost:8000`，在 Runtime console 中查询同一个 `run_id`。内置 Web 鉴权是 API Key；Cody 不包含企业 OAuth/SSO 登录产品，外部身份系统应通过反向代理或 Auth extension 接入。

## 4. 从不同入口操作同一个 Run

```bash
# 跟随事件
cody runs watch <run_id> --workdir /tmp/cody-tutorial

# 查看检查点和产物
cody timeline checkpoints <run_id> --workdir /tmp/cody-tutorial
cody artifacts list --run-id <run_id> --workdir /tmp/cody-tutorial

# 审批并恢复
cody approvals list --run-id <run_id> --status pending --workdir /tmp/cody-tutorial
cody approvals approve <approval_id> --workdir /tmp/cody-tutorial
cody runs resume <run_id> --workdir /tmp/cody-tutorial
```

## 5. HTTP 与实时事件

非 Python 客户端可以使用：

- `POST /run`：兼容 Agent 调用。
- `POST /run/stream`：SSE 流。
- `/runtime/*`：Canonical Runtime 查询与控制。
- `WS /ws`：双向实时运行与用户输入。
- `GET /health`：健康检查。

具体 request/response 和认证方式见 [HTTP API 指南](../API.md)。

## 验收标准

- CLI 启动的 Run 能在 Web 查询。
- Web 发起的审批能被 CLI 处理。
- 两个界面显示相同 event 顺序、状态和 Artifact。
- WebSocket 断线重连后从 event cursor 继续，不重复消费已提交事件。
- 所有入口使用同一规范化 workdir 和 Store 配置。
