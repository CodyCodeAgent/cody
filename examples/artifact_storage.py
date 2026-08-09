"""Store Runtime Artifact metadata in SQLite and payloads outside the catalog."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from cody.core.runtime import (
    ArtifactRecord,
    ArtifactType,
    FileSystemObjectStorage,
    RuntimeStoreBundle,
    S3ObjectStorage,
)


def s3_storage_from_env() -> S3ObjectStorage:
    bucket = os.environ["CODY_ARTIFACT_BUCKET"]
    return S3ObjectStorage(
        bucket,
        prefix=os.environ.get("CODY_ARTIFACT_PREFIX", "demo"),
        endpoint_url=os.environ.get("CODY_S3_ENDPOINT"),
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        put_options={"ServerSideEncryption": "AES256"},
    )


def run(backend: str) -> None:
    with TemporaryDirectory(prefix="cody-artifact-demo-") as temporary:
        root = Path(temporary)
        objects = (
            s3_storage_from_env()
            if backend == "s3"
            else FileSystemObjectStorage(root / "objects")
        )
        stores = RuntimeStoreBundle.sqlite(root / "runtime", object_storage=objects)
        artifact = ArtifactRecord(
            run_id="demo_artifact_storage",
            artifact_type=ArtifactType.TEST_REPORT,
            name="tests.json",
            content={"passed": 42, "failed": 0, "log": "all checks passed"},
        )
        stores.artifact_store.save(artifact)
        catalog = stores.artifact_store.catalog.get(artifact.artifact_id)
        hydrated = stores.artifact_store.get(artifact.artifact_id)
        assert catalog is not None
        assert hydrated is not None
        print("catalog payload:", catalog.content)
        print("hydrated payload:", hydrated.content)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("filesystem", "s3"), default="filesystem")
    args = parser.parse_args()
    run(args.backend)


if __name__ == "__main__":
    main()
