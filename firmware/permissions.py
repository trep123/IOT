import hmac

from rest_framework.permissions import BasePermission

from devices.models import Device


class IsAuthenticatedOrDevice(BasePermission):
    """升级包下载：管理端登录用户，或携带 device_id + secret 的设备。"""

    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            return True
        device_id = request.query_params.get("device_id") or request.headers.get("X-Device-Id")
        secret = request.query_params.get("secret") or request.headers.get("X-Device-Secret")
        if not device_id or not secret:
            return False
        device = Device.objects.filter(pk=device_id).only("secret").first()
        return bool(device and hmac.compare_digest(device.secret, secret))
