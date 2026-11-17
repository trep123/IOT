"""版本文件（升级包）存储：本地磁盘或 MinIO（S3 兼容），由 settings.STORAGES["packages"] 决定。"""
import logging
import time

from django.conf import settings
from django.core.files.storage import storages

log = logging.getLogger(__name__)


def package_storage():
    """FileField 的 storage 可调用对象：迁移文件里只记录函数路径，切换存储不需要新迁移。"""
    return storages["packages"]


def is_minio() -> bool:
    return settings.PACKAGE_STORAGE_BACKEND == "minio"


def _client():
    return package_storage().connection.meta.client


def ensure_bucket() -> bool:
    """MinIO 模式下确保存储桶存在；返回是否新建。"""
    if not is_minio():
        return False
    from botocore.exceptions import ClientError

    client, bucket = _client(), settings.MINIO["BUCKET"]
    try:
        client.head_bucket(Bucket=bucket)
        return False
    except ClientError as e:
        code = str(e.response.get("Error", {}).get("Code", ""))
        if code not in ("404", "NoSuchBucket", "NotFound"):
            raise
    client.create_bucket(Bucket=bucket)
    log.info("已创建 MinIO 存储桶 %s", bucket)
    return True


def wait_ready(timeout: float = 120) -> None:
    """等待对象存储可用（容器启动顺序）。"""
    deadline = time.monotonic() + timeout
    while True:
        try:
            ensure_bucket()
            return
        except Exception as e:  # noqa: BLE001
            if time.monotonic() > deadline:
                raise RuntimeError(f"MinIO 不可用：{e}") from e
            log.warning("等待 MinIO 就绪：%s", e)
            time.sleep(2)


def location(name: str) -> str:
    """文件的完整位置，用于界面展示。"""
    if not name:
        return ""
    if is_minio():
        prefix = settings.MINIO["PREFIX"]
        return f"minio://{settings.MINIO['BUCKET']}/{prefix + '/' if prefix else ''}{name}"
    return f"local://{name}"


def status() -> dict:
    """存储状态（管理端展示）。"""
    info = {"backend": settings.PACKAGE_STORAGE_BACKEND, "backend_display": "MinIO" if is_minio() else "本地磁盘",
            "endpoint": settings.MINIO["ENDPOINT"] if is_minio() else "", "bucket": settings.MINIO["BUCKET"] if is_minio() else "",
            "location": str(settings.MEDIA_ROOT) if not is_minio() else "", "reachable": True, "error": ""}
    if is_minio():
        try:
            _client().head_bucket(Bucket=settings.MINIO["BUCKET"])
        except Exception as e:  # noqa: BLE001
            info["reachable"], info["error"] = False, str(e)[:300]
    return info
