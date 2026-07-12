# Runtime Core 迭代记录

本目录是 canonical Runtime 从事件基础到产品主链的历史交付记录。文件编号表示实现
顺序，不是仍待完成的路线图；当前公共契约以 [Runtime 使用与部署](../RUNTIME.md)、
[架构设计](../ARCHITECTURE.md) 和代码为准。

## 阶段索引

| 阶段 | 迭代 | 主题 |
|------|------|------|
| 事件与持久化基础 | 001–006 | canonical events、TraceStore、Run/Step、SQLite、Checkpoint |
| Workflow 图与执行 | 007–014 | graph primitives、executor、adapter、template、async、resume |
| 生命周期与人工控制 | 015–020 | manager、registry、pause/cancel、approval、resume |
| Artifact 与调度 | 021–026 | artifact、tool policy、scheduler、multi-agent、quality、timeline |
| 产品接口与治理 | 027–032 | CLI/TUI/Web interface、authorization、auth、audit、store bundle |
| 统一生产主链 | 033–038 | runtime service、retry/fork/idempotency、并发团队、repair loop、共享产品表面 |

## 阅读规则

- 每篇 `Outcome`/交付内容说明当轮完成了什么。
- 后续迭代可能替换早期接口或实现；不要从单篇历史记录推断当前函数签名。
- 版本迁移和用户可见变化查阅根目录 [CHANGELOG](../../CHANGELOG.md)。
- 新迭代应继续递增编号，并同步更新本索引和当前用户文档。

**最后更新：2026-07-12**
