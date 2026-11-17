from django.db import models

from core import timeutil
from devices.models import Device

OTA_TEMPLATE_CODE = "OTA_UPGRADE"


class CommandTemplate(models.Model):
    template_id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    # 适用型号，["*"] 表示全部
    applicable_models = models.JSONField(default=list, blank=True)
    # 参数定义：{"字段": {"type": "int|float|str|bool", "required": true, "min": 0, "max": 100, "enum": [...]}}
    param_schema = models.JSONField(default=dict, blank=True)
    is_critical = models.BooleanField(default=False, help_text="关键操作：需二次确认并全量审计")
    timeout_seconds = models.PositiveIntegerField(default=30)
    is_system = models.BooleanField(default=False, help_text="系统内置（如升级通知），不可修改")
    description = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["template_id"]

    def __str__(self):
        return f"{self.code}({self.name})"


class CommandBatch(models.Model):
    class Status(models.TextChoices):
        RUNNING = "RUNNING", "执行中"
        COMPLETED = "COMPLETED", "已完成"
        PARTIAL_FAILED = "PARTIAL_FAILED", "部分失败"
        CANCELLED = "CANCELLED", "已取消"

    class OfflinePolicy(models.TextChoices):
        REJECT = "REJECT", "离线即失败"
        QUEUE = "QUEUE", "排队待上线"

    batch_id = models.BigAutoField(primary_key=True)
    template = models.ForeignKey(CommandTemplate, on_delete=models.PROTECT, db_column="template_id")
    params = models.JSONField(default=dict, blank=True)
    # 目标范围快照：原始条件 + 解析出的设备列表
    target_scope = models.JSONField(default=dict)
    offline_policy = models.CharField(max_length=8, choices=OfflinePolicy.choices, default=OfflinePolicy.REJECT)
    concurrency = models.PositiveIntegerField(default=20)
    total = models.IntegerField(default=0)
    success = models.IntegerField(default=0)
    failed = models.IntegerField(default=0)
    pending = models.IntegerField(default=0)
    cancelled = models.IntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING, db_index=True)
    retry_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="retries")
    operator_id = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timeutil.now)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-batch_id"]

    @property
    def success_rate(self):
        done = self.success + self.failed
        return round(self.success / done, 4) if done else None


class Command(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "待发送"
        SENT = "SENT", "已发送"
        DELIVERED = "DELIVERED", "已送达"
        SUCCESS = "SUCCESS", "执行成功"
        FAILED = "FAILED", "执行失败"
        TIMEOUT = "TIMEOUT", "超时"
        CANCELLED = "CANCELLED", "已取消"

    TERMINAL = {Status.SUCCESS, Status.FAILED, Status.TIMEOUT, Status.CANCELLED}
    INFLIGHT = {Status.SENT, Status.DELIVERED}

    command_id = models.BigAutoField(primary_key=True)
    batch = models.ForeignKey(CommandBatch, null=True, blank=True, on_delete=models.CASCADE,
                              related_name="commands", db_column="batch_id")
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="commands", db_column="device_id")
    template = models.ForeignKey(CommandTemplate, on_delete=models.PROTECT, db_column="template_id")
    params = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    result_code = models.IntegerField(null=True, blank=True)
    result_data = models.JSONField(null=True, blank=True)
    error_msg = models.CharField(max_length=255, blank=True, default="")
    operator_id = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timeutil.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-command_id"]
        indexes = [models.Index(fields=["device", "status"])]

    @property
    def is_terminal(self):
        return self.status in self.TERMINAL
