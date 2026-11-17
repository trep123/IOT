"""初始化版本文件存储：等待 MinIO 就绪并创建存储桶；可选把本地已有的升级包迁移到 MinIO。

    python manage.py storage_init              # 检查 / 建桶
    python manage.py storage_init --sync-local # 另把 MEDIA_ROOT 中的升级包上传到 MinIO（已存在的跳过）
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from firmware import storage
from firmware.models import UpgradePackage


class Command(BaseCommand):
    help = "初始化版本文件存储（MinIO 建桶、迁移本地升级包）"

    def add_arguments(self, parser):
        parser.add_argument("--sync-local", action="store_true", help="把本地 MEDIA_ROOT 中的升级包上传到 MinIO")
        parser.add_argument("--timeout", type=float, default=120, help="等待 MinIO 就绪的秒数")

    def handle(self, *args, **opts):
        if not storage.is_minio():
            self.stdout.write(f"版本文件存储：本地磁盘 {settings.MEDIA_ROOT}")
            return
        try:
            storage.wait_ready(opts["timeout"])
        except RuntimeError as e:
            raise CommandError(str(e))
        self.stdout.write(f"版本文件存储：MinIO {settings.MINIO['ENDPOINT']} 存储桶 {settings.MINIO['BUCKET']}（就绪）")
        if opts["sync_local"]:
            self._sync_local()

    def _sync_local(self):
        st = storage.package_storage()
        moved = missing = 0
        for pkg in UpgradePackage.objects.exclude(file_ref=""):
            name = pkg.file_ref.name
            if st.exists(name):
                continue
            local = Path(settings.MEDIA_ROOT) / name
            if not local.is_file():
                missing += 1
                self.stderr.write(f"  升级包 #{pkg.package_id} 本地文件不存在：{local}")
                continue
            with local.open("rb") as f:
                saved = st.save(name, f)
            if saved != name:
                pkg.file_ref.name = saved
                pkg.save(update_fields=["file_ref"])
            moved += 1
        self.stdout.write(f"本地升级包迁移到 MinIO：上传 {moved} 个，缺失 {missing} 个")
