from django.db import models

from core import timeutil


class OperationLog(models.Model):
    """操作审计：关键指令、批量控制、版本发布/回滚等统一记录。"""

    class OpType(models.TextChoices):
        CRITICAL_COMMAND = "CRITICAL_COMMAND", "关键指令下发"
        CRITICAL_COMMAND_RESULT = "CRITICAL_COMMAND_RESULT", "关键指令结果"
        BATCH_CONTROL = "BATCH_CONTROL", "批量控制"
        BATCH_CANCEL = "BATCH_CANCEL", "取消批次"
        VERSION_CREATE = "VERSION_CREATE", "创建版本"
        VERSION_PUBLISH = "VERSION_PUBLISH", "版本发布"
        VERSION_DEPRECATE = "VERSION_DEPRECATE", "版本废弃"
        PACKAGE_UPLOAD = "PACKAGE_UPLOAD", "上传升级包"
        UPGRADE_CREATE = "UPGRADE_CREATE", "创建升级任务"
        UPGRADE_START = "UPGRADE_START", "开始灰度"
        UPGRADE_PROMOTE = "UPGRADE_PROMOTE", "推进全量"
        UPGRADE_PAUSE = "UPGRADE_PAUSE", "暂停升级"
        UPGRADE_AUTO_PAUSE = "UPGRADE_AUTO_PAUSE", "失败率超阈值自动暂停"
        UPGRADE_RESUME = "UPGRADE_RESUME", "继续升级"
        UPGRADE_RETRY = "UPGRADE_RETRY", "重试失败设备"
        ROLLBACK = "ROLLBACK", "版本回滚"
        KEY_GENERATE = "KEY_GENERATE", "生成接入Key"
        KEY_REVOKE = "KEY_REVOKE", "吊销接入Key"
        KEY_VIEW = "KEY_VIEW", "查看接入Key"

    class TargetType(models.TextChoices):
        DEVICE = "DEVICE"
        COMMAND = "COMMAND"
        BATCH = "BATCH"
        VERSION = "VERSION"
        PACKAGE = "PACKAGE"
        TASK = "TASK"

    op_id = models.BigAutoField(primary_key=True)
    operator_id = models.CharField(max_length=64, db_index=True)
    op_type = models.CharField(max_length=32, choices=OpType.choices, db_index=True)
    target_type = models.CharField(max_length=16, choices=TargetType.choices)
    target_id = models.CharField(max_length=64, db_index=True)
    detail = models.JSONField(default=dict, blank=True)
    result = models.CharField(max_length=32, default="SUCCESS")
    op_time = models.DateTimeField(default=timeutil.now, db_index=True)

    class Meta:
        ordering = ["-op_time", "-op_id"]

    def __str__(self):
        return f"{self.operator_id} {self.op_type} {self.target_type}:{self.target_id}"


def record(operator, op_type, target_type, target_id, detail=None, result="SUCCESS") -> OperationLog:
    return OperationLog.objects.create(
        operator_id=operator or "system",
        op_type=op_type,
        target_type=target_type,
        target_id=str(target_id),
        detail=detail or {},
        result=result,
    )
