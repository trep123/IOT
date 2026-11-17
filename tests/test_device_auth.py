"""设备接入 Key：手动生成 / 吊销 / 批量生成，HMAC 签名上线与各类鉴权失败。"""
import time

import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator

from audit.models import OperationLog
from devices.auth import DeviceAuthError, authenticate, compute_sign
from devices.models import Device
from iot_platform.asgi import application


def signed(device_id, key, ts=None, nonce="nonce12345"):
    ts = str(ts or int(time.time()))
    return {"ts": ts, "nonce": nonce, "sign": compute_sign(key, device_id, ts, nonce)}


@pytest.mark.django_db(transaction=True)
def test_generate_view_revoke_key_with_audit(api, make_device, outbox):
    make_device("k1")
    assert api.get("/api/devices/k1/").data["has_key"] is False
    assert api.get("/api/devices/k1/secret/").data["secret"] is None

    k = api.post("/api/devices/k1/generate-key/").data
    assert len(k["secret"]) == 32 and k["key_created_at"]
    assert api.get("/api/devices/k1/secret/").data["secret"] == k["secret"]
    k2 = api.post("/api/devices/k1/generate-key/").data["secret"]
    assert k2 != k["secret"]  # 重新生成：旧 Key 失效
    assert api.get("/api/devices/", {"has_key": "true"}).data["count"] == 1

    r = api.post("/api/devices/k1/revoke-key/")
    assert r.data["secret"] is None and Device.objects.get(pk="k1").secret == ""
    assert api.get("/api/devices/", {"has_key": "false"}).data["count"] == 1
    ops = list(OperationLog.objects.filter(target_id="k1").values_list("op_type", flat=True))
    assert ops.count("KEY_GENERATE") == 2 and "KEY_REVOKE" in ops and "KEY_VIEW" in ops
    # 生成 / 吊销都会踢掉当前连接
    assert sum(1 for g, m in outbox.raw if g == "device.k1" and m["type"] == "device.kick") == 3


@pytest.mark.django_db(transaction=True)
def test_batch_generate_keys(api, make_device):
    make_device("b1"), make_device("b2")
    api.post("/api/devices/b2/generate-key/")
    r = api.post("/api/devices/generate-keys/", {"device_ids": ["b1", "b2", "nope"]}, format="json")
    assert [g["device_id"] for g in r.data["generated"]] == ["b1"]
    assert {s["device_id"]: s["reason"] for s in r.data["skipped"]} == {"b2": "已有 Key", "nope": "设备不存在"}
    r = api.post("/api/devices/generate-keys/", {"device_ids": ["b2"], "overwrite": True}, format="json")
    assert len(r.data["generated"]) == 1


@pytest.mark.django_db(transaction=True)
def test_authenticate_rules(settings, make_device):
    make_device("a1")
    with pytest.raises(DeviceAuthError) as e:
        authenticate("a1", signed("a1", "x" * 32))
    assert e.value.code == 4403  # 未生成 Key
    Device.objects.filter(pk="a1").update(secret="s" * 32)
    key = "s" * 32

    assert authenticate("a1", signed("a1", key)).device_id == "a1"
    cases = [
        ("a1", {}, 4400),
        ("a1", signed("a1", key, nonce="nonce12345"), 4409),                  # nonce 重放
        ("a1", signed("a1", "w" * 32, nonce="nonce-bad-key"), 4401),           # Key 错误
        ("a1", signed("a1", key, ts=int(time.time()) - 3600, nonce="nonce-old-ts"), 4408),  # 时间戳过期
        ("a1", {**signed("a1", key, nonce="nonce-fmt-1"), "ts": "abc"}, 4400),
        ("a1", signed("a2", key, nonce="nonce-other"), 4401),                 # 签名串里的设备编号不符
        ("nobody", signed("nobody", key, nonce="nonce-nobody"), 4401),
    ]
    for device_id, params, code in cases:
        with pytest.raises(DeviceAuthError) as e:
            authenticate(device_id, params)
        assert e.value.code == code, (params, e.value.message)

    assert authenticate("a1", {"secret": key})
    settings.IOT = {**settings.IOT, "DEVICE_AUTH_ALLOW_PLAIN": False}
    with pytest.raises(DeviceAuthError):
        authenticate("a1", {"secret": key})


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_websocket_signed_connect_and_no_key_rejected(user):
    await sync_to_async(Device.objects.create)(device_id="w1", name="w1", model="GW-100")
    ws = WebsocketCommunicator(application, "/ws/device/w1/?ts=1&nonce=abcdefgh&sign=00")
    await ws.connect()
    msg = await ws.receive_json_from(timeout=3)
    assert msg == {"type": "auth_failed", "code": 4403, "message": msg["message"]}

    key = "f" * 32
    await sync_to_async(Device.objects.filter(pk="w1").update)(secret=key)
    from urllib.parse import urlencode
    ws = WebsocketCommunicator(application, f"/ws/device/w1/?{urlencode(signed('w1', key, nonce='wsnonce0001'))}")
    connected, _ = await ws.connect()
    assert connected
    await ws.send_json_to({"type": "register", "version": "1.0.0"})
    assert (await ws.receive_json_from(timeout=3))["type"] == "registered"
    await ws.disconnect()
