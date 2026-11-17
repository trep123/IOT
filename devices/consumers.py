import json
import uuid
from urllib.parse import parse_qs

from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from django.db import close_old_connections, transaction

from core.realtime import device_group

from . import gateway, services
from .auth import DeviceAuthError, authenticate
from .models import Device


class DeviceGatewayConsumer(JsonWebsocketConsumer):
    """设备长连接：ws/device/<device_id>/?ts=&nonce=&sign=（鉴权见 devices/auth.py）。

    鉴权失败时先完成握手，发送 {"type": "auth_failed", "code", "message"} 再以 code 关闭，
    便于设备端定位原因（握手阶段直接拒绝只能得到 HTTP 403）。
    """

    authed = False

    @classmethod
    def encode_json(cls, content):
        # 中文按 UTF-8 原样发送：报文更短，嵌入式 JSON 库（如 Mongoose）也无需处理 \uXXXX 转义
        return json.dumps(content, ensure_ascii=False, separators=(",", ":"))

    def connect(self):
        close_old_connections()
        self.device_id = self.scope["url_route"]["kwargs"]["device_id"]
        qs = {k: v[0] for k, v in parse_qs(self.scope.get("query_string", b"").decode()).items()}
        try:
            authenticate(self.device_id, qs)
        except DeviceAuthError as e:
            self.accept()
            self.send_json({"type": "auth_failed", "code": e.code, "message": e.message})
            self.close(code=e.code)
            return
        self.connection_id = uuid.uuid4().hex
        Device.objects.filter(pk=self.device_id).update(connection_id=self.connection_id)
        group = device_group(self.device_id)
        # 顶替同一设备的旧连接
        async_to_sync(self.channel_layer.group_send)(group, {"type": "device.kick"})
        async_to_sync(self.channel_layer.group_add)(group, self.channel_name)
        self.authed = True
        self.accept()

    def receive_json(self, content, **kwargs):
        if not self.authed:
            return
        if not isinstance(content, dict):
            self.send_json({"type": "error", "message": "消息必须是 JSON 对象"})
            return
        close_old_connections()
        reply = gateway.handle_uplink(self.device_id, content)
        if reply:
            self.send_json(reply)

    def disconnect(self, code):
        if not self.authed:
            return
        async_to_sync(self.channel_layer.group_discard)(device_group(self.device_id), self.channel_name)
        close_old_connections()
        with transaction.atomic():
            services.disconnect(self.device_id, self.connection_id)

    # ---- Channel Layer 下行事件 ----
    def device_downlink(self, event):
        self.send_json(event["msg"])

    def device_kick(self, event):
        self.close(code=4000)
