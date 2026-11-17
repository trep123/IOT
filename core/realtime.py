"""设备通信通道（下行）与管理端实时推送。

所有消息都在数据库事务提交后才经 Channel Layer 发出（transaction.on_commit），
避免设备回执比数据落库更早到达。生产多节点部署时配置 REDIS_URL 即可跨进程投递。
"""
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

ADMIN_GROUP = "admin.events"


def device_group(device_id: str) -> str:
    return f"device.{device_id}"


def _group_send(group: str, message: dict) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(group, message)


def send_to_device(device_id: str, msg: dict) -> None:
    transaction.on_commit(lambda: _group_send(device_group(device_id), {"type": "device.downlink", "msg": msg}))


def kick_device(device_id: str) -> None:
    transaction.on_commit(lambda: _group_send(device_group(device_id), {"type": "device.kick"}))


def broadcast(event: str, data: dict) -> None:
    transaction.on_commit(lambda: _group_send(ADMIN_GROUP, {"type": "admin.event", "event": event, "data": data}))
