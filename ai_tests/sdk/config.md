# 配置管理测试

测试配置的加载、合并、覆盖机制。

---

## TC-CFG-001: 环境变量覆盖

**优先级**: P0
**前置条件**: cody 已安装
**涉及功能**: `Config.load()` 读取环境变量

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/cfg_001"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_env.py" << 'PYEOF'
import os
os.environ["CODY_MODEL"] = "test-model-env"
os.environ["CODY_MODEL_BASE_URL"] = "https://test.example.com/v1"

from cody.core.config import Config
config = Config.load()
print(f"MODEL: {config.model}")
print(f"BASE_URL: {config.model_base_url}")
print(f"MODEL_FROM_ENV: {config.model == 'test-model-env'}")
print(f"URL_FROM_ENV: {config.model_base_url == 'https://test.example.com/v1'}")
PYEOF
python3 "$TEST_DIR/test_env.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 环境变量成功覆盖配置

### 验证方法

```bash
grep "MODEL_FROM_ENV: True" "$TEST_DIR/output.log" && echo "PASS: model from env" || echo "FAIL"
grep "URL_FROM_ENV: True" "$TEST_DIR/output.log" && echo "PASS: url from env" || echo "FAIL"
```

---

## TC-CFG-002: 项目级配置覆盖全局

**优先级**: P0
**前置条件**: cody 已安装
**涉及功能**: 项目 `.cody/config.json` 覆盖全局配置

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/cfg_002"
mkdir -p "$TEST_DIR/.cody"
# 创建项目级配置
cat > "$TEST_DIR/.cody/config.json" << 'EOF'
{
  "model": "project-specific-model",
  "security": {
    "command_timeout": 99
  }
}
EOF
cat > "$TEST_DIR/test_project_config.py" << 'PYEOF'
import sys
from pathlib import Path
from cody.core.config import Config

workdir = Path(sys.argv[1])
config = Config.load(workdir=workdir)
print(f"MODEL: {config.model}")
print(f"IS_PROJECT_MODEL: {config.model == 'project-specific-model'}")
print(f"TIMEOUT: {config.security.command_timeout}")
print(f"IS_PROJECT_TIMEOUT: {config.security.command_timeout == 99}")
PYEOF
python3 "$TEST_DIR/test_project_config.py" "$TEST_DIR" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 项目级的 model 和 timeout 覆盖了全局配置

### 验证方法

```bash
grep "IS_PROJECT_MODEL: True" "$TEST_DIR/output.log" && echo "PASS: project model" || echo "FAIL"
grep "IS_PROJECT_TIMEOUT: True" "$TEST_DIR/output.log" && echo "PASS: project timeout" || echo "FAIL"
```

---

## TC-CFG-003: Config.is_ready() 检查

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: 配置就绪检查

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/cfg_003"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_ready.py" << 'PYEOF'
from cody.core.config import Config

# 空配置 — 应该 not ready
empty = Config()
print(f"EMPTY_READY: {empty.is_ready()}")
print(f"EMPTY_MISSING: {len(empty.missing_fields())}")

# 有 model 但没有 base_url — 仍然 not ready
partial = Config(model="test-model")
print(f"PARTIAL_READY: {partial.is_ready()}")

# 都有 — ready
full = Config(model="test-model", model_base_url="https://test.com/v1")
print(f"FULL_READY: {full.is_ready()}")
PYEOF
python3 "$TEST_DIR/test_ready.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 空配置不 ready
- 只有 model 不 ready
- model + base_url 才 ready

### 验证方法

```bash
grep "EMPTY_READY: False" "$TEST_DIR/output.log" && echo "PASS: empty not ready" || echo "FAIL"
grep "PARTIAL_READY: False" "$TEST_DIR/output.log" && echo "PASS: partial not ready" || echo "FAIL"
grep "FULL_READY: True" "$TEST_DIR/output.log" && echo "PASS: full is ready" || echo "FAIL"
```

---

## TC-CFG-004: CLI config show 隐藏 API Key

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `cody config show` 脱敏

### 操作步骤

```bash
cody config show 2>&1 | tee /tmp/cody_config_show.log
```

### 预期结果

- API Key 显示为 `***` 或部分隐藏，不泄露完整密钥

### 验证方法

```bash
# 完整的 key 不应该出现在输出中
if grep -q "sk-sp-9ecbb004a9cd4d288735137eee97bc27" /tmp/cody_config_show.log; then
    echo "FAIL: full API key exposed"
else
    echo "PASS: API key is masked"
fi
```
