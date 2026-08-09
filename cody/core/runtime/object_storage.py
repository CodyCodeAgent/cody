"""Object storage adapters for large Runtime artifact payloads."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import Any, Protocol

from .artifact import ArtifactRecord, ArtifactType


class ObjectStorage(Protocol):
    """Minimal blob contract implemented by filesystem and S3-compatible stores."""

    def put(self, key: str, data: bytes, *, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class FileSystemObjectStorage:
    """Process-safe object storage for local or shared-filesystem deployments."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError(f"Object key escapes storage root: {key}")
        return path

    def put(self, key: str, data: bytes, *, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(path)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3ObjectStorage:
    """S3-compatible adapter using an injected client or optional boto3."""

    def __init__(
        self,
        bucket: str,
        *,
        prefix: str = "cody",
        client: Any = None,
        put_options: dict[str, Any] | None = None,
        **client_kwargs: Any,
    ):
        if client is None:
            try:
                import boto3
            except ImportError as exc:
                raise RuntimeError("Install cody-ai[production] to use S3 storage") from exc
            client = boto3.client("s3", **client_kwargs)
        self.client = client
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.put_options = dict(put_options or {})

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def put(self, key: str, data: bytes, *, content_type: str) -> None:
        reserved = {"Bucket", "Key", "Body", "ContentType"}
        overlap = reserved.intersection(self.put_options)
        if overlap:
            names = ", ".join(sorted(overlap))
            raise ValueError(f"S3 put_options cannot override managed fields: {names}")
        self.client.put_object(
            Bucket=self.bucket,
            Key=self._key(key),
            Body=data,
            ContentType=content_type,
            **self.put_options,
        )

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=self._key(key))["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._key(key))


class ObjectArtifactStore:
    """Artifact metadata catalog backed by external object payload storage."""

    def __init__(self, catalog: Any, objects: ObjectStorage):
        self.catalog = catalog
        self.objects = objects

    def save(self, artifact: ArtifactRecord) -> ArtifactRecord:
        key = f"runs/{artifact.run_id}/artifacts/{artifact.artifact_id}.json"
        envelope = {"content": artifact.content}
        self.objects.put(
            key,
            json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
            content_type=artifact.mime_type,
        )
        metadata = dict(artifact.metadata)
        metadata.update({"object_key": key, "object_backed": True})
        catalog_record = replace(artifact, content={"object_key": key}, metadata=metadata)
        self.catalog.save(catalog_record)
        return artifact

    def get(self, artifact_id: str) -> ArtifactRecord | None:
        record = self.catalog.get(artifact_id)
        return self._hydrate(record) if record is not None else None

    def list(
        self,
        *,
        run_id: str | None = None,
        step_id: str | None = None,
        artifact_type: ArtifactType | None = None,
    ) -> list[ArtifactRecord]:
        return [
            self._hydrate(record)
            for record in self.catalog.list(
                run_id=run_id, step_id=step_id, artifact_type=artifact_type
            )
        ]

    def _hydrate(self, record: ArtifactRecord) -> ArtifactRecord:
        key = record.metadata.get("object_key")
        if not key:
            return record
        envelope = json.loads(self.objects.get(str(key)).decode("utf-8"))
        return replace(record, content=envelope["content"])
