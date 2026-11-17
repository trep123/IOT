"""设备接入鉴权（WebSocket 上线与升级包下载共用）。

推荐方式 —— HMAC 签名，Key 不在网络上传输：
    ts    = 当前 Unix 时间戳（秒）
    nonce = 每次连接随机生成的字符串（8~64 位字母数字）
    sign  = hex( HMAC-SHA256( key, f"{device_id}\\n{ts}\\n{nonce}" ) )
    ws://<host>/ws/device/<device_id>/?ts=<ts>&nonce=<nonce>&sign=<sign>

兼容方式 —— 明文 Key（IOT_DEVICE_AUTH_ALLOW_PLAIN=1 时可用）：
    ws://<host>/ws/device/<device_id>/?secret=<key>
"""
import hashlib
import hmac
import re

from django.conf import settings
from django.core.cache import cache

from core import timeutil

from .models import Device

NONCE_RE = re.compile(r"^[A-Za-z0-9_\-]{8,64}$")


class DeviceAuthError(Exception):
    """code 同时用作 WebSocket 关闭码。"""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def sign_payload(device_id: str, ts, nonce: str) -> str:
    return f"{device_id}\n{ts}\n{nonce}"


def compute_sign(key: str, device_id: str, ts, nonce: str) -> str:
    return hmac.new(key.encode(), sign_payload(device_id, ts, nonce).encode(), hashlib.sha256).hexdigest()


def authenticate(device_id: str, params: dict) -> Device:
    """params：ts / nonce / sign 或 secret。成功返回设备，失败抛 DeviceAuthError。"""
    sign, secret = params.get("sign") or "", params.get("secret") or ""
    if not sign and not secret:
        raise DeviceAuthError(4400, "缺少鉴权参数：需要 ts、nonce、sign（或 secret）")

    device = Device.objects.filter(pk=device_id).only("device_id", "secret").first()
    if device is None:
        raise DeviceAuthError(4401, "鉴权失败：设备不存在或 Key 错误")
    if not device.secret:
        raise DeviceAuthError(4403, "设备尚未生成接入 Key，请在管理端「设备详情 → 接入 Key」中生成")

    if sign:
        ts, nonce = str(params.get("ts") or ""), str(params.get("nonce") or "")
        if not ts.isdigit() or not NONCE_RE.match(nonce):
            raise DeviceAuthError(4400, "参数格式错误：ts 为 Unix 秒级时间戳，nonce 为 8~64 位字母数字")
        skew = settings.IOT["DEVICE_AUTH_MAX_SKEW"]
        if abs(timeutil.now().timestamp() - int(ts)) > skew:
            raise DeviceAuthError(4408, f"时间戳偏差超过 {skew} 秒，请校准设备时钟（NTP）")
        if not hmac.compare_digest(compute_sign(device.secret, device_id, ts, nonce), sign.lower()):
            raise DeviceAuthError(4401, "鉴权失败：签名错误（请检查 Key 与签名串格式）")
        # 防重放：同一 nonce 在时间窗口内只能使用一次
        if not cache.add(f"iot:nonce:{device_id}:{nonce}", 1, timeout=skew * 2):
            raise DeviceAuthError(4409, "nonce 已使用，请每次连接生成新的随机 nonce")
        return device

    if not settings.IOT["DEVICE_AUTH_ALLOW_PLAIN"]:
        raise DeviceAuthError(4401, "平台已关闭明文 Key 接入，请使用 HMAC 签名方式")
    if not hmac.compare_digest(device.secret, secret):
        raise DeviceAuthError(4401, "鉴权失败：设备不存在或 Key 错误")
    return device
