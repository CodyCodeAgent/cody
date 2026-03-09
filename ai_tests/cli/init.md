# Init 命令测试

测试 `cody init` 初始化功能。

---

## TC-INIT-001: 初始化新项目

**优先级**: P1
**前置条件**: cody 已安装，LLM 可用
**涉及功能**: `cody init` — 创建 .cody/ 目录和 CODY.md

### 操作步骤

1. 创建一个模拟项目：
```bash
TEST_DIR="$CODY_TEST_DIR/init_001"
mkdir -p "$TEST_DIR"
echo 'print("hello")' > "$TEST_DIR/main.py"
echo '[project]
name = "test-project"' > "$TEST_DIR/pyproject.toml"
```

2. 在项目目录执行 init（需要通过 workdir 指定，因为不能 cd）：
```bash
cat > "$TEST_DIR/run_init.py" << 'PYEOF'
import asyncio, os, sys
os.chdir(sys.argv[1])
from cody.core import Config
from cody.core.project_instructions import CODY_MD_FILENAME, generate_project_instructions
from pathlib import Path

async def main():
    workdir = Path(sys.argv[1])
    cody_dir = workdir / ".cody"
    cody_dir.mkdir(exist_ok=True)
    (cody_dir / "skills").mkdir(exist_ok=True)
    config = Config.load(workdir=workdir)
    config.save(cody_dir / "config.json")
    print("SCAFFOLD_OK: True")

    content = await generate_project_instructions(workdir, config)
    (workdir / CODY_MD_FILENAME).write_text(content)
    print(f"CODY_MD_OK: {bool(content)}")
    print(f"CODY_MD_LEN: {len(content)}")

asyncio.run(main())
PYEOF
python3 "$TEST_DIR/run_init.py" "$TEST_DIR" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- `.cody/` 目录被创建
- `.cody/skills/` 目录被创建
- `.cody/config.json` 被创建
- `CODY.md` 被创建且有内容

### 验证方法

```bash
test -d "$TEST_DIR/.cody" && echo "PASS: .cody/ exists" || echo "FAIL: no .cody/"
test -d "$TEST_DIR/.cody/skills" && echo "PASS: skills/ exists" || echo "FAIL: no skills/"
test -f "$TEST_DIR/.cody/config.json" && echo "PASS: config.json exists" || echo "FAIL: no config"
test -f "$TEST_DIR/CODY.md" && echo "PASS: CODY.md exists" || echo "FAIL: no CODY.md"
test -s "$TEST_DIR/CODY.md" && echo "PASS: CODY.md has content" || echo "FAIL: empty CODY.md"
```
