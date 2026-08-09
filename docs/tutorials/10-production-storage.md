# 10 · PostgreSQL 与 S3/MinIO

<div class="tutorial-outcome"><strong>完成后：</strong>你会把 Runtime catalog 放入 PostgreSQL，把大型 Artifact payload 外置到 S3-compatible storage。</div>

## 1. 安装生产适配器

```bash
pip install 'cody-ai[production]'
```

该 extra 安装 PostgreSQL 与 S3 客户端，不会自动部署数据库、MinIO、TLS、备份或高可用。

## 2. 配置 PostgreSQL Store

```python
import os

from cody import CodyRuntime
from cody.core import Config
from cody.core.runtime import RuntimeStoreBundle

workdir = "/srv/projects/payments"
dsn = os.environ["CODY_POSTGRES_DSN"]

stores = RuntimeStoreBundle.postgres(
    dsn,
    schema="agent_runtime",
)
runtime = CodyRuntime.from_config(
    Config.load(workdir=workdir),
    workdir,
    stores=stores,
)
```

PostgreSQL catalog 保存 Run、Step、Event、Checkpoint、Approval、Artifact metadata、Audit 与 Control，适合多个服务进程共享状态。

## 3. 外置 Artifact payload

```python
import os

from cody.core.runtime import RuntimeStoreBundle, S3ObjectStorage

objects = S3ObjectStorage(
    bucket=os.environ["CODY_ARTIFACT_BUCKET"],
    prefix="production/tenant-a",
    endpoint_url=os.environ.get("CODY_S3_ENDPOINT"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
    put_options={"ServerSideEncryption": "AES256"},
)

stores = RuntimeStoreBundle.postgres(
    os.environ["CODY_POSTGRES_DSN"],
    schema="agent_runtime",
    object_storage=objects,
)
```

MinIO 使用同一 S3-compatible adapter，只需提供 endpoint 和相应凭据。数据库保留 metadata/object key，读取 Artifact 时自动回填 payload。

## 4. 不要硬编码凭据

DSN、access key 和 secret key只通过部署环境或 secret manager 注入。不要把它们放进：

- Prompt
- Workflow metadata
- event payload
- Artifact 内容
- `.cody/config.json`
- 示例、截图或 CI 日志

## 5. 做跨进程验证

最小验收不是“连接成功”，而是：

1. 进程 A 创建 Run、Event、Checkpoint 和待审批记录。
2. 进程 B 使用同一 schema 查询并批准。
3. 进程 A 退出后，进程 C 能恢复 Run。
4. Artifact catalog 中只有 object key，大型 payload 在对象存储。
5. 不同 tenant prefix 不可互相枚举。
6. PostgreSQL 与对象存储都启用 TLS、最小权限、备份和生命周期策略。

项目内置可重复验证脚本：

```bash
python scripts/verify_production_backends.py --help
```

该脚本从环境变量读取凭据，JSON 结果不会输出 secret，并区分 `PASS`、`SKIP` 与 contract-only 验证。
