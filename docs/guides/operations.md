# 运行观测与故障处理

每次排障都从 `run_id` 开始。不要先翻散落日志；先判断 Run 当前状态、最后一个已提交事件和最近 checkpoint。

## 快速诊断

```bash
cody runs show <run_id> --workdir /path/to/project
cody runs metrics <run_id> --workdir /path/to/project
cody timeline show <run_id> --workdir /path/to/project
cody timeline checkpoints <run_id> --workdir /path/to/project
cody artifacts list --run-id <run_id> --workdir /path/to/project
cody approvals list --run-id <run_id> --workdir /path/to/project
```

## 状态决策表

| 状态 | 先检查 | 常见操作 |
|---|---|---|
| `running` | 最近 event、worker 心跳/进程、Control | 正常等待；孤儿 Run 用 `recover` |
| `waiting` | pending Approval / human input | approve/reject 后 `resume` |
| `paused` | pause checkpoint、sandbox snapshot | `resume` 或从 checkpoint `fork` |
| `failed` | error event、失败 step、Review Artifact | 修复根因后 `retry` |
| `cancelled` | cancel actor 与传播结果 | 确认副作用后按需 `retry` |
| `completed` | gate、artifact、usage 与最终输出 | 交付或从历史 checkpoint `fork` |

## Timeline 应回答的问题

- 当前在哪个 workflow node？
- 为什么选择了这个分支、Agent 或工具？
- 哪次模型/工具调用失败并触发重试？
- 是否在等待审批、暂停或预算耗尽？
- 最近哪个 checkpoint 可以恢复？
- 产物、测试报告和审计记录是否完整关联？

## Metrics

至少持续观察：

- Run 与 node duration
- 模型 input/output/total tokens
- 成本（仅在 provider usage 可换算时）
- 模型与节点 retry 次数
- Tool 成功率、超时和拒绝率
- Quality Gate 通过率与返修次数
- Artifact 数量与对象存储体积
- waiting / paused Run 数量与等待时长

## 常见故障

### Run 一直显示 running

先确认 owning worker 是否仍存活；如果已终止，使用 `recover`。不要对仍有活跃 worker 的 Run 同时启动第二个恢复进程。

### Approval 已批准但没有继续

确认批准写入了同一个 Store 和规范化 workdir，然后执行 `runs resume`。检查恢复进程是否注册了原 Workflow 所需的自定义 handler。

### 恢复后工具重复执行

检查工具是否通过 Runtime Tool Registry、是否存在 receipt，以及业务幂等键是否稳定。仅凭“最近日志看起来执行过”不能安全去重。

### 找不到 Artifact payload

Catalog 中可能只保存 object key。检查对象存储 endpoint、tenant prefix、凭据、生命周期和 snapshot 引用是否过期。

### Sandbox 行为与预期不一致

检查 event 中的实际 backend。若配置允许 fallback，可能已经落到 `local-policy`；生产环境应使用 `fail_if_unavailable=true`。

## 审计要求

Audit 至少关联 actor、service account、project、run、step、action、decision 与脱敏后的参数。脱敏是最后防线，不应代替“不把 secret 放入 payload”的设计。
