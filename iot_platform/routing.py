from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
from django.urls import re_path

from core.consumers import AdminEventConsumer
from devices.consumers import DeviceGatewayConsumer

websocket_urlpatterns = [
    # 设备端：设备不带浏览器 Origin，以设备密钥鉴权
    re_path(r"^ws/device/(?P<device_id>[A-Za-z0-9_.\-]{1,64})/$", DeviceGatewayConsumer.as_asgi()),
    # 管理端：校验 Origin，支持 Session 或 ?token= 鉴权
    re_path(r"^ws/admin/$", AllowedHostsOriginValidator(AuthMiddlewareStack(AdminEventConsumer.as_asgi()))),
]
