from django.db import models

from core import timeutil
from devices.models import Device


class FirmwareVersion(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "草稿"
        RELEASABLE = "RELEASABLE", "可发布"
        DEPRECATED = "DEPRECATED", "已废弃"

    version_id = models.BigAutoField(primary_key=True)
    version_no = models.CharField(max_length=32, unique=True)
    applicable_models = models.JSONField(default=list)
    min_upgradable_version = models.CharField(max_length=32, blank=True, default="",
                                              help_text="低于此版本的设备不能直接升级到本版本")
    release_notes = models.TextField(blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    created_at = models.DateTimeField(default=timeutil.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-version_id"]

    def __str__(self):
        return self.version_no


def package_upload_to(instance, filename):
    return f"packages/{instance.version.version_no}/{timeutil.now():%Y%m%d%H%M%S}_{filename}"


class UpgradePackage(models.Model):
    class PackageType(models.TextChoices):
        FULL = "FULL", "全量包"
        DIFF = "DIFF", "差分包"

    package_id = models.BigAutoField(primary_key=True)
    version = models.ForeignKey(FirmwareVersion, on_delete=models.CASCADE, related_name="packages",
                                db_column="version_id")
    package_type = models.CharField(max_length=8, choices=PackageType.choices)
    base_version = models.CharField(max_length=32, blank=True, default="", help_text="差分包的起始版本")
    file_ref = models.FileField(upload_to=package_upload_to, max_length=255)
    file_name = models.CharField(max_length=255)
    size = models.BigIntegerField(default=0)
    checksum = models.CharField(max_length=64, help_text="SHA-256")
    signature = models.CharField(max_length=64, help_text="HMAC-SHA256(checksum)")
    verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timeutil.now)

    class Meta:
        ordering = ["-package_id"]


class UpgradeTask(models.Model):
    class TaskType(models.TextChoices):
        UPGRADE = "UPGRADE", "升级"
        ROLLBACK = "ROLLBACK", "回滚"

    class Status(models.TextChoices):
        CREATED = "CREATED", "已创建"
        GRAY = "GRAY", "灰度中"
        FULL = "FULL", "全量中"
        PAUSED = "PAUSED", "已暂停"
        COMPLETED = "COMPLETED", "已完成"
        ROLLED_BACK = "ROLLED_BACK", "已回滚"

    ACTIVE = {Status.GRAY, Status.FULL}
    OPEN = {Status.CREATED, Status.GRAY, Status.FULL, Status.PAUSED}

    task_id = models.BigAutoField(primary_key=True)
    version = models.ForeignKey(FirmwareVersion, on_delete=models.PROTECT, related_name="tasks",
                                db_column="version_id")
    task_type = models.CharField(max_length=16, choices=TaskType.choices, default=TaskType.UPGRADE)
    parent_task = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="rollback_tasks")
    target_scope = models.JSONField(default=dict)
    gray_ratio = models.FloatField(default=0.1)
    gray_device_ids = models.JSONField(default=list, blank=True)
    failure_threshold = models.FloatField(default=0.2, help_text="失败率阈值，超过自动暂停")
    failure_baseline = models.IntegerField(default=0, help_text="人工继续时已确认的失败数，不再计入阈值")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CREATED, db_index=True)
    paused_from = models.CharField(max_length=16, blank=True, default="")
    pause_reason = models.CharField(max_length=255, blank=True, default="")
    excluded = models.JSONField(default=list, blank=True, help_text="自动排除的设备及原因")
    operator_id = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timeutil.now)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-task_id"]


class DeviceUpgradeRecord(models.Model):
    class Stage(models.TextChoices):
        WAITING = "WAITING", "等待"
        DOWNLOADING = "DOWNLOADING", "下载中"
        VERIFYING = "VERIFYING", "校验中"
        INSTALLING = "INSTALLING", "安装中"
        REBOOTING = "REBOOTING", "重启中"
        SUCCESS = "SUCCESS", "成功"
        FAILED = "FAILED", "失败"

    ORDER = [Stage.WAITING, Stage.DOWNLOADING, Stage.VERIFYING, Stage.INSTALLING, Stage.REBOOTING, Stage.SUCCESS]
    TERMINAL = {Stage.SUCCESS, Stage.FAILED}
    RUNNING = {Stage.DOWNLOADING, Stage.VERIFYING, Stage.INSTALLING, Stage.REBOOTING}

    class Phase(models.TextChoices):
        GRAY = "GRAY", "灰度"
        FULL = "FULL", "全量"

    record_id = models.BigAutoField(primary_key=True)
    task = models.ForeignKey(UpgradeTask, on_delete=models.CASCADE, related_name="records", db_column="task_id")
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="upgrade_records",
                               db_column="device_id")
    from_version = models.CharField(max_length=32, blank=True, default="")
    to_version = models.CharField(max_length=32)
    package = models.ForeignKey(UpgradePackage, null=True, on_delete=models.SET_NULL, db_column="package_id")
    phase = models.CharField(max_length=8, choices=Phase.choices, default=Phase.FULL)
    command_id = models.BigIntegerField(null=True, blank=True, help_text="升级通知复用的控制指令")
    stage = models.CharField(max_length=16, choices=Stage.choices, default=Stage.WAITING, db_index=True)
    progress = models.PositiveSmallIntegerField(default=0)
    error_msg = models.CharField(max_length=255, blank=True, default="")
    retry_count = models.PositiveIntegerField(default=0)
    notify_attempts = models.PositiveIntegerField(default=0)
    stage_changed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["record_id"]
        indexes = [models.Index(fields=["task", "stage"]), models.Index(fields=["device", "stage"])]
