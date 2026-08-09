"""Verify that two Runtime bundles observe the same PostgreSQL state."""

from __future__ import annotations

import argparse
import os
from uuid import uuid4

from cody.core.runtime import RunRecord, RunStatus, RuntimeStoreBundle


def run(dsn: str, schema: str) -> None:
    run_id = f"demo_postgres_{uuid4().hex}"
    writer = RuntimeStoreBundle.postgres(dsn, schema=schema)
    reader = RuntimeStoreBundle.postgres(dsn, schema=schema)
    writer.run_store.save_run(
        RunRecord(
            task="verify cross-process visibility",
            run_id=run_id,
            status=RunStatus.RUNNING,
        )
    )
    writer.control_store.request_cancel(run_id, before_node_id="deploy")

    observed = reader.run_store.get_run(run_id)
    assert observed is not None
    cancel_visible = reader.control_store.should_cancel(run_id, "deploy")
    reader.control_store.clear_cancel(run_id)
    print("run_id:", observed.run_id)
    print("status:", observed.status.value)
    print("cross-instance cancel visible:", cancel_visible)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("CODY_POSTGRES_DSN"))
    parser.add_argument("--schema", default="agent_runtime")
    args = parser.parse_args()
    if not args.dsn:
        parser.error("set CODY_POSTGRES_DSN or pass --dsn")
    run(args.dsn, args.schema)


if __name__ == "__main__":
    main()
