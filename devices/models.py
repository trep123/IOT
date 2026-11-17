import secrets

from django.core.validators import RegexValidator
from django.db import models

from core import timeutil

device_id_validator = RegexValidator(r"^[A-Za-z0-9_.\-]{1,64}$", "设备编号只能包含字母、数字、下划线、点和短横线。")


def new_secret() -> str:
    """设备接入 Key：32 位十六进制，由管理员手动生成。"""
    return secrets.token_hex(16)


class DeviceGroup(models.Model):
    group_id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=64, unique=True)
    description = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(default=timeutil.now)

    class Meta:
        ordering = ["group_id"]

    def __str__(self):
        return self.name


class Device(models.Model):
    """设备档案：平台唯一数据源。"""

    class OnlineStatus(models.TextChoices):
        ONLINE = "ONLINE", "在线"
        OFFLINE = "OFFLINE", "离线"

    device_id = models.CharField(max_length=64, primary_key=True, validators=[device_id_validator])
    name = models.CharField(max_length=128)
    model = models.CharField(max_length=64, db_index=True)
    group = models.ForeignKey(DeviceGroup, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="devices", db_column="group_id")
    current_version = models.CharField(max_length=32, blank=True, default="", db_index=True)
    online_status = models.CharField(max_length=8, choices=OnlineStatus.choices,
                                     default=OnlineStatus.OFFLINE, db_index=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    last_online_at = models.DateTimeField(null=True, blank=True)
    last_offline_at = models.DateTimeField(null=True, blank=True)
    # 设备接入 Key（管理员手动生成；为空表示未生成，设备无法上线）
    secret = models.CharField(max_length=64, blank=True, default="")
    secret_created_at = models.DateTimeField(null=True, blank=True)
    # 当前有效连接标识，用于区分重连时旧连接的断开事件
    connection_id = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(default=timeutil.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["device_id"]

    def __str__(self):
        return f"{self.device_id}({self.name})"

    @property
    def has_key(self) -> bool:
        return bool(self.secret)

    @property
    def is_online(self) -> bool:
        return self.online_status == self.OnlineStatus.ONLINE


class DeviceStatusLog(models.Model):
    class Reason(models.TextChoices):
        REGISTER = "REGISTER", "主动上线"
        HEARTBEAT_RESUME = "HEARTBEAT_RESUME", "心跳恢复"
        DISCONNECT = "DISCONNECT", "主动断开"
        HEARTBEAT_TIMEOUT = "HEARTBEAT_TIMEOUT", "心跳超时"

    log_id = models.BigAutoField(primary_key=True)
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="status_logs",
                               db_column="device_id")
    from_status = models.CharField(max_length=8, choices=Device.OnlineStatus.choices)
    to_status = models.CharField(max_length=8, choices=Device.OnlineStatus.choices)
    reason = models.CharField(max_length=32, choices=Reason.choices)
    # 变更前状态的持续时长（秒），例如上线时记录本次离线持续了多久
    duration_seconds = models.IntegerField(null=True, blank=True)
    occurred_at = models.DateTimeField(default=timeutil.now, db_index=True)

    class Meta:
        ordering = ["-occurred_at", "-log_id"]
