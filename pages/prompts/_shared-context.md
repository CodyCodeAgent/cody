# Cody 项目公共上下文（所有 SDK 教程 prompt 共用）

## 项目是什么

Cody 是一个**开源 AI Coding Agent 框架**（Python），让开发者能快速构建、定制和部署自己的 AI 编程 Agent。

- GitHub: https://github.com/CodyCodeAgent/cody
- PyPI: `pip install cody-ai`
- 版本: v2.0.2 · MIT 开源

核心特点：
- 30 个内置工具（文件读写、grep/glob、Shell 执行、LSP 代码智能、Web 抓取等）
- 多模型支持（Claude、OpenAI、Gemini、DeepSeek、通义千问、智谱 GLM 等）
- Agent Skills 开放标准（兼容 Claude Code、Cursor 等 26+ 平台）
- 完整安全体系（权限控制、路径保护、熔断器、审计日志）
- 四种接入方式：Python SDK（主推）/ CLI / TUI / Web

---

## ⚠️ 重要：本教程系列的演示模型

**本系列所有教程使用 通义千问 qwen3.5-plus 作为演示模型。**

环境变量配置（推荐读者按此配置后运行示例）：
```bash
export CODY_MODEL=qwen3.5-plus
export CODY_MODEL_API_KEY=sk-xxx        # 阿里云百炼 / Coding API Key
export CODY_MODEL_BASE_URL=https://coding.dashscope.aliyuncs.com/v1
```

代码方式显式配置（教程中展示完整客户端初始化时使用）：
```python
from cody.sdk import Cody

client = (
    Cody()
    .workdir("/path/to/project")
    .model("qwen3.5-plus")
    .base_url("https://coding.dashscope.aliyuncs.com/v1")
    .api_key("sk-xxx")
    .build()
)
```

**写教程正文时的原则**：
1. 所有涉及客户端创建的示例，使用 `qwen3.5-plus` + `https://coding.dashscope.aliyuncs.com/v1`，**不使用 Claude**
2. 简短示例可以用 `AsyncCodyClient(workdir=".")` 不指定模型（靠环境变量），更简洁
3. 不要出现 `claude-sonnet-4-0`、`sk-ant-xxx` 这类 Anthropic 示例
4. 国产模型在该教程体系里是**首选**，不是"第三方选项"

---

## 网站是什么

这是 Cody 的官方静态网站（GitHub Pages），由纯 HTML/CSS/JS 构成，无需构建工具。

文件结构：
```
pages/
  index.html       ← 产品介绍页
  docs.html        ← 文档中心（门户）
  sdk.html         ← SDK 教程索引（13 篇）
  sdk/             ← SDK 教程文章（你要写的）
    _template.html ← 文章页面 HTML 框架
    01-single-run.html
    02-multi-turn.html
    ...
  style.css        ← 全局样式
  script.js        ← 交互逻辑
```

---

## 设计规范

### 颜色变量（CSS 自定义属性）
```
--blue:        #52c4f7   ← 主色，链接、高亮
--green:       #4ade80
--purple:      #a78bfa
--yellow:      #fbbf24
--red:         #f87171
--bg-0:        #050810   ← 最深背景
--bg-1:        #0a0e1a   ← 页面主背景
--bg-card:     #111827   ← 卡片背景
--bg-code:     #0d1117   ← 代码块背景
--border:      rgba(255,255,255,0.07)
--text-primary:   #f0f6fc
--text-secondary: #8b949e
--text-muted:     #484f58
--text-code:      #79c0ff
```

### 字体
- 标题/正文：`Sora`, `Inter`（Google Fonts 已引入）
- 代码：`JetBrains Mono`（Google Fonts 已引入）

### 可用 HTML 组件

**代码块**（必须带 Copy 按钮）：
```html
<div class="code-block">
  <button class="copy-btn" aria-label="复制代码">Copy</button>
  <pre><span class="cm"># 注释</span>
<span class="kw">from</span> cody <span class="kw">import</span> AsyncCodyClient

<span class="kw">async def</span> <span class="fn">main</span>():
    result = <span class="kw">await</span> client.run(<span class="str">"任务"</span>)
    <span class="nb">print</span>(result.output)</pre>
</div>
```

**语法高亮 span 类**（用在 `<pre>` 内）：
| 类名 | 颜色 | 用途 |
|------|------|------|
| `.kw` | 红色 | 关键字：`from import async await def class with try except` |
| `.fn` | 紫色 | 函数名：`main`, `run`, `fetch_data` |
| `.str` | 蓝色 | 字符串：`"hello"`, `'sk-ant-...'` |
| `.cm` | 灰斜体 | 注释：`# 这是注释` |
| `.nb` | 橙色 | 内置/参数：`print`, `workdir`, `session_id` |
| `.t-prompt` | 绿色 | 终端提示符：`$ ` |

**提示框**：
```html
<div class="callout callout-tip">💡 提示文字</div>
<div class="callout callout-info">ℹ️ 信息文字</div>
<div class="callout callout-warn">⚠️ 警告文字</div>
```

**参数表**：
```html
<table class="param-table">
  <thead>
    <tr><th>参数</th><th>类型</th><th>必填</th><th>说明</th></tr>
  </thead>
  <tbody>
    <tr>
      <td>workdir</td>
      <td>str</td>
      <td>否</td>
      <td>工作目录，默认当前目录 <code>.</code></td>
    </tr>
  </tbody>
</table>
```

**徽章**：
```html
<span class="badge badge-blue">文字</span>
<span class="badge badge-green">文字</span>
<span class="badge badge-purple">文字</span>
<span class="badge badge-yellow">文字</span>
```

**内联代码**：`<code>client.run()</code>`

---

## 教程文章的写作风格

1. **叙事教学**：不是罗列 API，而是"带着读者做一件事"
2. **代码先行**：先给完整可运行示例，再解释细节
3. **有始有终**：开头说"本篇你会学到什么"，结尾给下一篇指引
4. **中文写作**：所有正文中文，代码注释中文，变量名/函数名保持英文
5. **简洁准确**：不重复废话，不写显而易见的注释
6. **适度深度**：不过于简化（读者是 Python 开发者），也不过于学术

---

## 所有篇目列表（供侧边栏和上下篇导航参考）

| 篇号 | 文件名 | 标题 | 所属分组 |
|------|--------|------|---------|
| 01 | 01-single-run.html | 一次性对话 | 基础篇 |
| 02 | 02-multi-turn.html | 多轮对话 | 基础篇 |
| 03 | 03-streaming.html | 流式输出全解 | 基础篇 |
| 04 | 04-tools.html | 工具直接调用 | 工具篇 |
| 05 | 05-custom-tools.html | 注册自定义工具 | 工具篇 |
| 06 | 06-prompt.html | Prompt 定制与多模态 | 定制篇 |
| 07 | 07-skills.html | 使用 Skills | 定制篇 |
| 08 | 08-mcp.html | 集成 MCP | 定制篇 |
| 09 | 09-security.html | 安全与控制 | 进阶篇 |
| 10 | 10-events.html | 事件与可观测性 | 进阶篇 |
| 11 | 11-memory.html | 项目记忆 | 进阶篇 |
| 12 | 12-human-in-loop.html | 人机协同 | 进阶篇 |
| 13 | 13-storage.html | 存储抽象 | 进阶篇 |
