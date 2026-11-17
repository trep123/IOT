"""版本文件存储：本地磁盘与 MinIO。

MinIO 用例需要可用的 MinIO（或兼容服务），通过环境变量启用：
    IOT_TEST_MINIO_ENDPOINT=http://127.0.0.1:9000 IOT_TEST_MINIO_ACCESS_KEY=… IOT_TEST_MINIO_SECRET_KEY=… pytest
"""
import hashlib
import os
import uuid

import pytest
from django.core.files.storage import storages

from firmware.models import UpgradePackage

pytestmark = pytest.mark.django_db(transaction=True)

MINIO_ENDPOINT = os.getenv("IOT_TEST_MINIO_ENDPOINT", "")


def _upload(api, firmware_file, content=b"firmware-v2", version_no="2.0.0"):
    vid = api.post("/api/firmware-versions/", {"version_no": version_no, "applicable_models": ["GW-100"]},
                   format="json").data["version_id"]
    r = api.post("/api/upgrade-packages/", {"version_id": vid, "package_type": "FULL",
                                            "file": firmware_file(content, "固件 v2.bin"),
                                            "checksum": hashlib.sha256(content).hexdigest()}, format="multipart")
    assert r.status_code == 201, r.data
    return vid, r.data


def _download(api, pkg_id):
    r = api.get(f"/api/upgrade-packages/{pkg_id}/download/")
    assert r.status_code == 200
    return b"".join(r.streaming_content), r


def test_local_storage(api, firmware_file, settings):
    st = api.get("/api/upgrade-packages/storage/").data
    assert st["backend"] == "local" and st["reachable"]
    vid, pkg = _upload(api, firmware_file)
    assert pkg["storage_location"].startswith("local://packages/2.0.0/")
    body, resp = _download(api, pkg["package_id"])
    assert body == b"firmware-v2" and resp["Content-Length"] == str(len(body))
    assert "filename*=UTF-8''" in resp["Content-Disposition"]
    assert api.get("/api/upgrade-packages/storage/").data["package_count"] == 1
    # 删除草稿版本时一并删除文件
    path = settings.MEDIA_ROOT / UpgradePackage.objects.get().file_ref.name
    assert path.exists()
    assert api.delete(f"/api/firmware-versions/{vid}/").status_code == 204
    assert not path.exists()


@pytest.fixture
def minio(settings):
    if not MINIO_ENDPOINT:
        pytest.skip("未设置 IOT_TEST_MINIO_ENDPOINT")
    bucket = f"iot-test-{uuid.uuid4().hex[:8]}"
    settings.MINIO = {"ENDPOINT": MINIO_ENDPOINT, "ACCESS_KEY": os.environ["IOT_TEST_MINIO_ACCESS_KEY"],
                      "SECRET_KEY": os.environ["IOT_TEST_MINIO_SECRET_KEY"], "BUCKET": bucket,
                      "REGION": "us-east-1", "PREFIX": ""}
    settings.PACKAGE_STORAGE_BACKEND = "minio"
    settings.STORAGES = {**settings.STORAGES, "packages": {"BACKEND": "storages.backends.s3.S3Storage", "OPTIONS": {
        "endpoint_url": MINIO_ENDPOINT, "access_key": settings.MINIO["ACCESS_KEY"],
        "secret_key": settings.MINIO["SECRET_KEY"], "bucket_name": bucket, "region_name": "us-east-1",
        "addressing_style": "path", "signature_version": "s3v4", "file_overwrite": False, "default_acl": None}}}
    field = UpgradePackage._meta.get_field("file_ref")
    old = field.storage
    field.storage = storages["packages"]   # FileField 在类定义时就解析了 storage，测试中替换
    from firmware import storage
    storage.ensure_bucket()
    client = field.storage.connection.meta.client
    yield client, bucket
    field.storage = old
    for obj in client.list_objects_v2(Bucket=bucket).get("Contents", []):
        client.delete_object(Bucket=bucket, Key=obj["Key"])
    client.delete_bucket(Bucket=bucket)


def test_minio_storage(api, firmware_file, minio):
    client, bucket = minio
    st = api.get("/api/upgrade-packages/storage/").data
    assert st["backend"] == "minio" and st["bucket"] == bucket and st["reachable"], st
    vid, pkg = _upload(api, firmware_file, content=b"x" * (3 * 1024 * 1024 + 7))
    assert pkg["storage_location"].startswith(f"minio://{bucket}/packages/2.0.0/")
    key = UpgradePackage.objects.get().file_ref.name
    head = client.head_object(Bucket=bucket, Key=key)
    assert head["ContentLength"] == 3 * 1024 * 1024 + 7
    body, resp = _download(api, pkg["package_id"])
    assert hashlib.sha256(body).hexdigest() == pkg["checksum"]
    assert api.post(f"/api/upgrade-packages/{pkg['package_id']}/verify/").data["verified"] is True
    # 对象被外部删除 → 重新校验不通过、下载 404
    client.delete_object(Bucket=bucket, Key=key)
    assert api.post(f"/api/upgrade-packages/{pkg['package_id']}/verify/").data["verified"] is False
    assert api.get(f"/api/upgrade-packages/{pkg['package_id']}/download/").status_code == 404
    # 删除升级包同时删除对象
    _, pkg2 = _upload(api, firmware_file, content=b"v3", version_no="3.0.0")
    key2 = UpgradePackage.objects.get(package_id=pkg2["package_id"]).file_ref.name
    assert api.delete(f"/api/upgrade-packages/{pkg2['package_id']}/").status_code == 204
    assert client.list_objects_v2(Bucket=bucket, Prefix=key2).get("KeyCount", 0) == 0


def test_minio_unreachable(api, settings):
    settings.MINIO = {**settings.MINIO, "ENDPOINT": "http://127.0.0.1:1", "BUCKET": "iot"}
    settings.PACKAGE_STORAGE_BACKEND = "minio"
    settings.STORAGES = {**settings.STORAGES, "packages": {"BACKEND": "storages.backends.s3.S3Storage", "OPTIONS": {
        "endpoint_url": "http://127.0.0.1:1", "access_key": "a", "secret_key": "b", "bucket_name": "iot",
        "addressing_style": "path"}}}
    from botocore.config import Config  # noqa: F401  确认 boto3 已安装
    st = api.get("/api/upgrade-packages/storage/").data
    assert st["backend"] == "minio" and st["reachable"] is False and st["error"]
