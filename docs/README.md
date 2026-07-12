# Cody 文档索引

本文档目录以 Cody 2.0.2 的代码为准。CLI、TUI、Web 和 SDK 都是 Canonical
Runtime 的产品表面；历史评审和迭代记录不作为当前 API 规范。

## 从这里开始

| 目标 | 文档 |
|------|------|
| 15 分钟跑通 Cody | [快速入门](QUICKSTART.md) |
| 使用命令行 | [CLI 使用指南](CLI.md) |
| 嵌入 Python 应用 | [SDK 使用指南](SDK.md) |
| 编排、恢复和治理 Run | [Runtime 使用与部署](RUNTIME.md) |
| 配置进程隔离 | [Sandbox 指南](SANDBOX.md) |
| 使用浏览器或 HTTP/WS | [HTTP API](API.md) 与 [Web 开发](../web/README.md) |

## 参考文档

- [配置详解](CONFIG.md)：配置文件、环境变量、权限、Sandbox 和安全边界。
- [功能清单](FEATURES.md)：当前能力、产品表面和版本演进。
- [架构设计](ARCHITECTURE.md)：依赖方向、canonical execution path 和数据流。
- [技能开发](SKILLS.md)：Agent Skills 的创建、发现、启停和分发。
- [TUI 指南](TUI.md)：Textual 界面、快捷键和运行状态展示。
- [贡献指南](../CONTRIBUTING.md)：开发环境、测试、代码规范和提交要求。
- [CHANGELOG](../CHANGELOG.md)：发布级变更历史。

## 文档类型与权威性

| 类型 | 目录/文件 | 用途 |
|------|-----------|------|
| 当前用户文档 | `README.md`、`docs/*.md`、`web/README.md` | 说明当前可用行为 |
| 黑盒测试手册 | `ai_tests/` | 人工或 Agent 驱动的产品回归步骤 |
| 内置 Skill | `cody/skills/*/SKILL.md` | 运行时加载的 Agent 指令，不是用户手册 |
| 历史迭代记录 | `docs/iterations/` | 记录每轮设计与交付，不承诺当前 API 形态 |
| 历史评审/需求 | `AGENT_KERNEL_REVIEW.md`、`HARNESS.md` | 保留决策背景；当前状态以代码和本索引为准 |
| 教程生成源 | `pages/prompts/` | 生成站点教程的源稿，不替代 API 文档 |

## 文档维护规则

每次改变公共行为时，至少同步检查：

1. `README.md` 和 `QUICKSTART.md` 是否仍能从零跑通。
2. CLI 参数是否与实际 `cody <command> --help` 一致。
3. SDK/Runtime 示例是否能被当前导入路径和函数签名接受。
4. `CONFIG.md` 是否与 `cody/core/config.py` 的字段和默认值一致。
5. HTTP 端点是否与 `web/backend/routes/` 一致。
6. 不在文档、测试夹具或日志中写入真实密钥。
7. 运行文档检查：Markdown 本地链接、Python fenced code 编译、Ruff 和测试。

**最后更新：2026-07-12**
