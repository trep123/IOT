from rest_framework.permissions import BasePermission

from devices.auth import DeviceAuthError, authenticate


class IsAuthenticatedOrDevice(BasePermission):
    """升级包下载：管理端登录用户，或通过接入 Key 鉴权的设备。

    设备参数与上线一致（query 或请求头 X-Device-Id / X-Device-Ts / X-Device-Nonce / X-Device-Sign /
    X-Device-Secret）：device_id + ts + nonce + sign，或 device_id + secret。
    """
    message = "需要登录，或提供设备鉴权参数（device_id + ts/nonce/sign）。"

    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            return True

        def p(name):
            return request.query_params.get(name) or request.headers.get(f"X-Device-{name.capitalize()}")
        device_id = request.query_params.get("device_id") or request.headers.get("X-Device-Id")
        if not device_id:
            return False
        try:
            authenticate(device_id, {k: p(k) for k in ("ts", "nonce", "sign", "secret")})
        except DeviceAuthError as e:
            self.message = e.message
            return False
        return True
