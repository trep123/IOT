import pytest

from core import timeutil
from core.scheduler import run_scan
from devices.models import Device, DeviceStatusLog

pytestmark = pytest.mark.django_db(transaction=True)


def test_create_device_without_key_and_standard_pagination(api):
    r = api.post("/api/devices/", {"device_id": "dev-1", "name": "一号", "model": "GW-100",
                                   "current_version": "1.0.0"}, format="json")
    assert r.status_code == 201, r.data
    assert r.data["secret"] is None and r.data["has_key"] is False  # Key 需手动生成
    r2 = api.post("/api/devices/", {"device_id": "dev-2", "name": "二号", "model": "GW-100",
                                    "generate_key": True}, format="json")
    assert len(r2.data["secret"]) == 32 and r2.data["has_key"] is True
    assert r.data["online_status"] == "OFFLINE"

    r = api.get("/api/devices/")
    assert r.status_code == 200
    assert set(r.data) == {"count", "next", "previous", "results"}
    assert all("secret" not in row for row in r.data["results"])


def test_online_status_cannot_be_set_manually(api, make_device):
    make_device("dev-1")
    r = api.patch("/api/devices/dev-1/", {"online_status": "ONLINE", "name": "改名"}, format="json")
    assert r.status_code == 200
    d = Device.objects.get(pk="dev-1")
    assert d.online_status == "OFFLINE" and d.name == "改名"


def test_register_heartbeat_timeout_and_status_logs(api, make_device, outbox):
    d, sim = make_device("dev-1")
    reply = sim.register("1.0.1")
    assert reply["type"] == "registered"
    d.refresh_from_db()
    assert d.online_status == "ONLINE" and d.current_version == "1.0.1"
    assert outbox.events("device_status")[-1]["online_status"] == "ONLINE"

    timeutil.shift(20)
    sim.heartbeat()
    timeutil.shift(25)  # 距最近心跳 25s < 30s
    run_scan()
    d.refresh_from_db()
    assert d.online_status == "ONLINE"

    timeutil.shift(10)  # 35s > 周期10 × N3
    run_scan()
    d.refresh_from_db()
    assert d.online_status == "OFFLINE"
    assert any(g == "device.dev-1" and m["type"] == "device.kick" for g, m in outbox.raw)

    sim.heartbeat()  # 心跳恢复
    logs = list(DeviceStatusLog.objects.filter(device_id="dev-1").order_by("log_id"))
    assert [(l.to_status, l.reason) for l in logs] == [
        ("ONLINE", "REGISTER"), ("OFFLINE", "HEARTBEAT_TIMEOUT"), ("ONLINE", "HEARTBEAT_RESUME")]
    assert logs[1].duration_seconds == 55  # 在线持续时长

    r = api.get("/api/devices/dev-1/status-logs/")
    assert r.data["count"] == 3


def test_filters_and_export(api, make_device):
    make_device("a1", model="GW-100", version="1.0.0", online=True)
    make_device("a2", model="GW-100", version="1.1.0")
    make_device("b1", model="CAM-1", version="1.0.0")
    r = api.get("/api/devices/", {"online_status": "OFFLINE", "model": "GW-100"})
    assert [x["device_id"] for x in r.data["results"]] == ["a2"]
    r = api.get("/api/devices/", {"version": "1.0.0", "ordering": "-device_id"})
    assert [x["device_id"] for x in r.data["results"]] == ["b1", "a1"]
    r = api.get("/api/devices/", {"search": "b1"})
    assert r.data["count"] == 1
    r = api.get("/api/devices/summary/")
    assert r.data["total"] == 3 and r.data["online"] == 1
    r = api.get("/api/devices/export/", {"model": "GW-100"})
    assert r.status_code == 200 and r["Content-Type"].startswith("text/csv")
    assert r.content.decode("utf-8-sig").count("\n") == 3


def test_requires_authentication(transactional_db):
    from rest_framework.test import APIClient
    assert APIClient().get("/api/devices/").status_code == 401
