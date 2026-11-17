"""设备上行消息处理（协议见 docs/protocol.md）。与传输层无关，WebSocket / MQTT 桥接均可复用。"""
from django.conf import settings
from django.db import transaction

from core import timeutil

from . import services
from .models import Device


def handle_uplink(device_id: str, msg: dict, now=None) -> dict | None:
    now = now or timeutil.now()
    mtype = msg.get("type")
    with transaction.atomic():
        device = Device.objects.select_for_update().filter(pk=device_id).first()
        if device is None:
            return {"type": "error", "message": "设备不存在"}

        if mtype == "register":
            services.register(device, msg, now)
            return {"type": "registered", "server_time": now.isoformat(),
                    "heartbeat_interval": settings.IOT["HEARTBEAT_INTERVAL"]}
        if mtype == "heartbeat":
            services.heartbeat(device, now)
            return None
        # 业务消息同时视作一次心跳
        services.heartbeat(device, now)

        if mtype == "ack":
            from control import services as control
            control.handle_ack(device, msg.get("command_id"), now)
            return None
        if mtype == "result":
            from control import services as control
            control.handle_result(device, msg.get("command_id"), msg.get("code"), msg.get("data"),
                                  msg.get("message"), now)
            return None
        if mtype == "upgrade_progress":
            from firmware import services as firmware
            firmware.handle_progress(device, msg.get("record_id"), msg.get("stage"), msg.get("progress"),
                                     msg.get("error"), now)
            return None
        if mtype == "version_report":
            services.report_version(device, str(msg.get("version") or ""), now)
            return None
    return {"type": "error", "message": f"未知消息类型: {mtype}"}
