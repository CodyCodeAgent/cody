from io import BytesIO
import json

import pytest

from cody.core.runtime import (
    ArtifactRecord,
    ArtifactType,
    FileSystemObjectStorage,
    RuntimeStoreBundle,
    S3ObjectStorage,
)


def test_object_backed_artifact_keeps_payload_out_of_sqlite_catalog(tmp_path):
    objects = FileSystemObjectStorage(tmp_path / "objects")
    stores = RuntimeStoreBundle.sqlite(tmp_path / "runtime", object_storage=objects)
    artifact = ArtifactRecord(
        run_id="run_object",
        artifact_type=ArtifactType.TEST_REPORT,
        name="report.json",
        content={"log": "large-output", "passed": True},
    )

    stores.artifact_store.save(artifact)

    hydrated = stores.artifact_store.get(artifact.artifact_id)
    catalog_record = stores.artifact_store.catalog.get(artifact.artifact_id)
    assert hydrated is not None
    assert hydrated.content == artifact.content
    assert catalog_record.content == {
        "object_key": f"runs/run_object/artifacts/{artifact.artifact_id}.json"
    }
    assert catalog_record.metadata["object_backed"] is True


def test_filesystem_object_storage_rejects_path_escape(tmp_path):
    objects = FileSystemObjectStorage(tmp_path / "objects")

    try:
        objects.put("../secret", b"no", content_type="text/plain")
    except ValueError as exc:
        assert "escapes storage root" in str(exc)
    else:
        raise AssertionError("path escape should be rejected")


def test_s3_object_storage_round_trips_runtime_artifact_through_boto3(tmp_path):
    boto3 = pytest.importorskip("boto3")
    from botocore.response import StreamingBody
    from botocore.stub import Stubber

    client = boto3.client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    stubber = Stubber(client)
    artifact = ArtifactRecord(
        artifact_id="artifact_s3",
        run_id="run_s3",
        artifact_type=ArtifactType.TEST_REPORT,
        name="report.json",
        content={"passed": True, "log": "S3_LIVE_OK"},
    )
    key = "live/runs/run_s3/artifacts/artifact_s3.json"
    body = json.dumps({"content": artifact.content}, ensure_ascii=False).encode()
    stubber.add_response(
        "put_object",
        {},
        {
            "Bucket": "cody-test",
            "Key": key,
            "Body": body,
            "ContentType": "application/json",
        },
    )
    stubber.add_response(
        "get_object",
        {"Body": StreamingBody(BytesIO(body), len(body))},
        {"Bucket": "cody-test", "Key": key},
    )
    stubber.add_response(
        "delete_object",
        {},
        {"Bucket": "cody-test", "Key": key},
    )
    stubber.activate()
    objects = S3ObjectStorage("cody-test", prefix="live", client=client)
    stores = RuntimeStoreBundle.sqlite(tmp_path / "runtime", object_storage=objects)

    stores.artifact_store.save(artifact)
    hydrated = stores.artifact_store.get(artifact.artifact_id)
    objects.delete("runs/run_s3/artifacts/artifact_s3.json")

    assert hydrated is not None
    assert hydrated.content == artifact.content
    stubber.assert_no_pending_responses()
