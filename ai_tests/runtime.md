# Canonical Runtime 与 Sandbox 黑盒测试

本组验证 Cody 2.x 的权威执行主链。真实模型 case 优先使用
`scripts/verify_live_capabilities.py`；外部生产后端必须使用真实服务，不得用 mock 代替。

## TC-RUNTIME-001：真实模型能力矩阵

**优先级**：P0  
**前置条件**：已按 [setup.md](setup.md) 安全提供 DeepSeek 测试 Key。

### 操作步骤

```bash
export CODY_LIVE_API_KEY="$CODY_MODEL_API_KEY"
export CODY_LIVE_BASE_URL="$CODY_MODEL_BASE_URL"
uv run python scripts/verify_live_capabilities.py | tee /tmp/cody-live-report.json
unset CODY_LIVE_API_KEY
```

### 预期结果

- 进程退出码为 0。
- 每个 case 的 `status` 都是 `passed`。
- 报告包含真实 `run_id`、token usage 和各表面的可观察证据。
- 报告不包含 API Key。

### 验证方法

```bash
python - <<'PY'
import json
from pathlib import Path

checks = json.loads(Path('/tmp/cody-live-report.json').read_text())
assert checks
assert all(item['status'] == 'passed' for item in checks)
print(f"PASS: {len(checks)} live cases")
PY
```

## TC-RUNTIME-002：跨进程恢复与治理回归

**优先级**：P0

### 操作步骤

```bash
uv run pytest -q \
  tests/test_runtime_process_recovery.py \
  tests/test_runtime_surfaces.py \
  tests/test_runtime_service.py \
  tests/test_runtime_redaction.py \
  tests/test_audit.py \
  tests/test_sandbox.py \
  tests/test_runtime_object_storage.py
```

### 预期结果

- 子进程被 `os._exit` 终止后，新进程从最后 committed checkpoint 恢复。
- waiting approval 可由新 Runtime 批准并恢复，不重复副作用工具。
- pause/cancel control 可跨 store instance 生效。
- retry/fork 保留 lineage，事件和审计中的 secrets 被脱敏。
- 当前平台真实 Sandbox case 通过；不可用后端 fail closed。

## TC-RUNTIME-003：CLI 与 Web 共享 Run

**优先级**：P0

### 操作步骤

1. 用 `cody run --workdir "$CODY_TEST_DIR" "回复 RUNTIME_OK"` 启动运行。
2. 执行 `cody runs list --workdir "$CODY_TEST_DIR" --json` 取得 `run_id`。
3. 执行 `cody runs show`、`runs metrics`、`timeline show` 和 `artifacts list`。
4. 启动 `cody-web run --port 18923`，通过 `/runtime/runs?workdir=...` 查询同一 Run。

### 预期结果

- CLI 和 Web 返回相同 `run_id` 与终态。
- timeline 具有 canonical event；metrics、checkpoint 和 artifact 可用同一 ID 关联。

## TC-RUNTIME-004：真实 PostgreSQL

**优先级**：P1  
**前置条件**：提供临时 PostgreSQL DSN；安装 `cody-ai[production]`。

### 验证要求

- 使用 `RuntimeStoreBundle.postgres(dsn)` 启动、等待审批、关闭进程并恢复 Run。
- 两个独立进程能看到相同 control/approval/event。
- 检查 schema/table/index 已创建，连接使用 TLS/最小权限账号。
- 报告只记录服务类型和版本，不记录 DSN 密码。

没有真实 DSN 时必须标记 `SKIP (external dependency)`，不能用 fake cursor 的通过结果替代。

## TC-RUNTIME-005：真实 S3/MinIO Artifact

**优先级**：P1  
**前置条件**：临时 endpoint、bucket 和短期凭证。

### 验证要求

- `S3ObjectStorage` 写入、读取、列出关联 Artifact，并删除测试对象。
- 数据库 catalog 只含 object key/metadata，不含完整 payload。
- 验证 bucket policy、tenant prefix 和服务端加密。

没有真实服务时必须标记 `SKIP (external dependency)`；boto3 Stubber 仅证明 adapter contract。

## TC-RUNTIME-006：真实容器/Linux/远程 Sandbox

**优先级**：P1

| 后端 | 必须验证 |
|------|----------|
| Docker/Podman | readonly 系统、workspace mount、no-network、CPU/memory/PID、timeout、process-tree cleanup |
| Bubblewrap | mount namespace、越界写入和网络阻断、fail-closed |
| Remote | create/exec/snapshot/pause/restore/fork/terminate，重启后 snapshot reference 仍有效 |

当前机器缺少对应 binary/service 时逐项标记 SKIP，并记录缺失命令或 endpoint。

## 清理

```bash
rm -f /tmp/cody-live-report.json
rm -rf "$CODY_TEST_DIR"
unset CODY_LIVE_API_KEY CODY_MODEL_API_KEY
```
