# 环境准备

在执行测试用例之前，AI 需要完成以下环境检查。

## 第 0 步：向用户获取 LLM 配置

> **重要**：每次执行 AI 黑盒测试前，必须先向用户询问以下三个配置项。
> 不要从环境变量或配置文件中猜测，直接问用户要。

**向用户提问（一次性问完）：**

```
在开始黑盒测试之前，需要你提供 LLM 配置：

1. CODY_MODEL — 目标 OpenAI-compatible 端点支持的模型名称（如 deepseek-v4-flash）
2. CODY_MODEL_API_KEY — API Key
3. CODY_MODEL_BASE_URL — API Base URL（如 https://xxx.xxx/v1）
```

拿到配置后，通过当前进程环境注入。不要把真实值写入脚本、Markdown、配置文件、
shell history 或测试报告：

```bash
export CODY_MODEL="<用户提供的值>"
export CODY_MODEL_API_KEY="<通过安全输入取得的值>"
export CODY_MODEL_BASE_URL="<用户提供的值>"
```

> **贯穿整个测试流程**：后续所有 `cody run`、`python3` 脚本等命令执行时，
> 都必须确保这三个环境变量已 export，否则 cody 无法调用 LLM。

## 检查步骤

### 1. 确认 cody 已安装

```bash
cody --version
```

**验证**：输出应包含版本号（当前代码为 `3.0.0`）。如果命令不存在，尝试：

```bash
# 检查项目 venv 中是否有
/Users/bytedance/GC/GitHub/cody/.venv/bin/cody --version
```

如果 venv 中有，后续所有命令使用 venv 路径：
```bash
export PATH="/Users/bytedance/GC/GitHub/cody/.venv/bin:$PATH"
```

如果都没有，执行安装：
```bash
cd /Users/bytedance/GC/GitHub/cody && pip install -e ".[dev,cli,web]"
```

### 2. 确认 LLM 连通性

```bash
cody run "回复 OK"
```

**验证**：应在 60 秒内返回包含 "OK" 的响应。如果超时或报错，让用户检查配置。

### 3. 创建测试工作目录

```bash
export CODY_TEST_DIR="/tmp/cody_ai_test_$(date +%s)"
mkdir -p "$CODY_TEST_DIR"
```

**验证**：目录已创建。后续所有测试用例都在此目录下操作。

### 4. 确认 Python 可用（SDK 测试需要）

```bash
python3 -c "import cody; print(cody.__version__)"
```

**验证**：输出版本号，无 ImportError。

### 5. 确认 Web 后端可启动（Web 测试需要）

> 此步骤仅在执行 `web/` 目录下的测试时需要。

```bash
# 在后台启动 web 后端
cd /Users/bytedance/GC/GitHub/cody && cody-web run --port 18923 &
WEB_PID=$!
sleep 3

# 检查健康端点
curl -s http://localhost:18923/health

# 停掉（检查完即可，测试时再启动）
kill $WEB_PID 2>/dev/null
```

**验证**：`/health` 返回 JSON，包含 `status` 字段。

### 6. 准备真实 LSP 依赖（完整 Runtime 回归需要）

`scripts/verify_live_capabilities.py` 的 LSP case 需要可执行的
`pyright-langserver`、`typescript-language-server` 和 `gopls`。TypeScript 必须固定在
稳定的 5.x；不要直接安装未固定版本，因为 TypeScript 7 的包结构不再包含 verifier
要求的 `lib/tsserver.js`。

```bash
mkdir -p /tmp/cody-lsp-live /tmp/cody-lsp-bin
npm install --prefix /tmp/cody-lsp-live \
  pyright@1.1.411 typescript-language-server@5.3.0 typescript@5.9.3
GOBIN=/tmp/cody-lsp-bin go install golang.org/x/tools/gopls@v0.18.1

export PATH="/tmp/cody-lsp-bin:/tmp/cody-lsp-live/node_modules/.bin:$PATH"
export CODY_LIVE_TYPESCRIPT_PACKAGE="/tmp/cody-lsp-live/node_modules/typescript"
test -f "$CODY_LIVE_TYPESCRIPT_PACKAGE/lib/tsserver.js"
```

若官方 Go proxy 在当前网络不可达，可显式使用组织允许的 mirror；报告必须记录所用
`gopls` 版本。缺少语言服务器时应标记 `SKIP (external dependency)`，不能把“未启动、
返回空 diagnostics”记为通过。

## 环境检查汇总

AI 执行完上述步骤后，应输出环境检查报告：

```
## 环境检查报告

| 检查项 | 结果 | 备注 |
|--------|------|------|
| LLM 配置 | PASS | 用户已提供 model/key/url |
| cody 安装 | PASS | v3.0.0 |
| LLM 连通 | PASS | 响应正常 |
| 测试目录 | PASS | /tmp/cody_ai_test_xxx |
| Python SDK | PASS | v3.0.0 |
| Web 后端 | SKIP | 未执行 web 测试 |
```

只有前 4 项全部 PASS 才可继续执行测试。
