"""设备在线管理：上线/离线判定、状态变更留痕、实时推送，并通知控制与升级模块。"""
from django.conf import settings

from core import realtime, timeutil

from .models import Device, DeviceStatusLog

ONLINE = Device.OnlineStatus.ONLINE
OFFLINE = Device.OnlineStatus.OFFLINE


def device_brief(d: Device) -> dict:
    return {
        "device_id": d.device_id,
        "name": d.name,
        "model": d.model,
        "online_status": d.online_status,
        "current_version": d.current_version,
        "last_heartbeat_at": d.last_heartbeat_at.isoformat() if d.last_heartbeat_at else None,
    }


def _since(ts, now):
    return int((now - ts).total_seconds()) if ts else None


def set_online(device: Device, reason: str, now=None) -> bool:
    now = now or timeutil.now()
    if device.online_status == ONLINE:
        return False
    DeviceStatusLog.objects.create(device=device, from_status=OFFLINE, to_status=ONLINE, reason=reason,
                                   duration_seconds=_since(device.last_offline_at, now), occurred_at=now)
    device.online_status = ONLINE
    device.last_online_at = now
    if not device.last_heartbeat_at or device.last_heartbeat_at < now:
        device.last_heartbeat_at = now
    device.save(update_fields=["online_status", "last_online_at", "last_heartbeat_at", "updated_at"])
    realtime.broadcast("device_status", {**device_brief(device), "reason": reason})

    # 上线触发：排队指令下发、挂起的升级继续
    from control import services as control
    from firmware import services as firmware
    control.on_device_online(device, now)
    firmware.on_device_online(device, now)
    return True


def set_offline(device: Device, reason: str, now=None, kick: bool = False) -> bool:
    now = now or timeutil.now()
    if device.online_status == OFFLINE:
        return False
    DeviceStatusLog.objects.create(device=device, from_status=ONLINE, to_status=OFFLINE, reason=reason,
                                   duration_seconds=_since(device.last_online_at, now), occurred_at=now)
    device.online_status = OFFLINE
    device.last_offline_at = now
    device.save(update_fields=["online_status", "last_offline_at", "updated_at"])
    realtime.broadcast("device_status", {**device_brief(device), "reason": reason})
    if kick:
        realtime.kick_device(device.device_id)
    return True


def heartbeat(device: Device, now=None) -> None:
    now = now or timeutil.now()
    device.last_heartbeat_at = now
    device.save(update_fields=["last_heartbeat_at", "updated_at"])
    if device.online_status == OFFLINE:
        set_online(device, DeviceStatusLog.Reason.HEARTBEAT_RESUME, now)


def register(device: Device, payload: dict, now=None) -> None:
    """设备注册：先回写上报的版本号（升级版本确认），再置上线（触发挂起任务）。"""
    now = now or timeutil.now()
    version = payload.get("version")
    if version:
        report_version(device, str(version), now)
    device.last_heartbeat_at = now
    device.save(update_fields=["last_heartbeat_at", "updated_at"])
    if device.online_status == ONLINE:
        # 已在线的设备重新注册（如重启后快速重连），也视为一次上线机会
        from control import services as control
        from firmware import services as firmware
        control.on_device_online(device, now)
        firmware.on_device_online(device, now)
    else:
        set_online(device, DeviceStatusLog.Reason.REGISTER, now)


def report_version(device: Device, version: str, now=None) -> None:
    now = now or timeutil.now()
    if version != device.current_version:
        device.current_version = version
        device.save(update_fields=["current_version", "updated_at"])
        realtime.broadcast("device_version", device_brief(device))
    from firmware import services as firmware
    firmware.on_version_report(device, version, now)


def disconnect(device_id: str, connection_id: str, now=None) -> None:
    device = Device.objects.select_for_update().filter(pk=device_id).first()
    if device and device.connection_id == connection_id:
        set_offline(device, DeviceStatusLog.Reason.DISCONNECT, now)


def scan_heartbeat_timeouts(now=None) -> int:
    """定时扫描：超过 心跳周期 × N 未收到心跳的在线设备判定离线。"""
    now = now or timeutil.now()
    from datetime import timedelta
    cfg = settings.IOT
    deadline = now - timedelta(seconds=cfg["HEARTBEAT_INTERVAL"] * cfg["HEARTBEAT_MISS_COUNT"])
    count = 0
    for device in Device.objects.select_for_update().filter(online_status=ONLINE, last_heartbeat_at__lt=deadline):
        if set_offline(device, DeviceStatusLog.Reason.HEARTBEAT_TIMEOUT, now, kick=True):
            count += 1
    return count


# ---------------------------------------------------------------- 接入 Key（管理员手动生成）
def generate_key(device: Device, operator: str = "system", now=None, regenerate_reason: str = "") -> str:
    """生成 / 重新生成接入 Key。旧 Key 立即失效，已建立的连接被断开，设备需用新 Key 重新上线。"""
    from audit.models import OperationLog, record

    from .models import new_secret

    had_key = bool(device.secret)
    device.secret = new_secret()
    device.secret_created_at = now or timeutil.now()
    device.save(update_fields=["secret", "secret_created_at", "updated_at"])
    realtime.kick_device(device.device_id)
    record(operator, OperationLog.OpType.KEY_GENERATE, OperationLog.TargetType.DEVICE, device.device_id,
           {"regenerate": had_key, **({"reason": regenerate_reason} if regenerate_reason else {})})
    realtime.broadcast("device_key", {"device_id": device.device_id, "has_key": True})
    return device.secret


def revoke_key(device: Device, operator: str = "system") -> None:
    """吊销接入 Key：设备立即下线且无法再上线，直到重新生成。"""
    from audit.models import OperationLog, record

    device.secret = ""
    device.secret_created_at = None
    device.save(update_fields=["secret", "secret_created_at", "updated_at"])
    realtime.kick_device(device.device_id)
    record(operator, OperationLog.OpType.KEY_REVOKE, OperationLog.TargetType.DEVICE, device.device_id)
    realtime.broadcast("device_key", {"device_id": device.device_id, "has_key": False})
