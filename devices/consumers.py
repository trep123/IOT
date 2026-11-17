import hmac
import uuid
from urllib.parse import parse_qs

from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from django.db import close_old_connections, transaction

from core.realtime import device_group

from . import gateway, services
from .models import Device


class DeviceGatewayConsumer(JsonWebsocketConsumer):
    """设备长连接：ws/device/<device_id>/?secret=<设备密钥>。上行走 gateway，下行由 Channel Layer 投递。"""

    authed = False

    def connect(self):
        close_old_connections()
        self.device_id = self.scope["url_route"]["kwargs"]["device_id"]
        qs = parse_qs(self.scope.get("query_string", b"").decode())
        secret = (qs.get("secret") or [""])[0]
        device = Device.objects.filter(pk=self.device_id).first()
        if device is None or not hmac.compare_digest(device.secret, secret):
            self.close(code=4401)
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
