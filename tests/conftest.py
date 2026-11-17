import os

os.environ.setdefault("IOT_EMBEDDED_SCHEDULER", "0")

import pytest  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

from core import realtime, timeutil  # noqa: E402
from devices import gateway  # noqa: E402
from devices.models import Device  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.IOT = {**settings.IOT, "HEARTBEAT_INTERVAL": 10, "HEARTBEAT_MISS_COUNT": 3,
                    "DEFAULT_BATCH_CONCURRENCY": 2, "UPGRADE_STAGE_TIMEOUT": 600, "QUEUE_TTL": 3600}
    timeutil.reset()
    yield
    timeutil.reset()


@pytest.fixture
def outbox(monkeypatch):
    """截获经 Channel Layer 发出的下行消息与管理端事件。"""
    sent = []
    monkeypatch.setattr(realtime, "_group_send", lambda group, message: sent.append((group, message)))

    class Box(list):
        def to_device(self, device_id, mtype=None):
            return [m["msg"] for g, m in sent if g == f"device.{device_id}" and m["type"] == "device.downlink"
                    and (mtype is None or m["msg"]["type"] == mtype)]

        def events(self, name):
            return [m["data"] for g, m in sent if m["type"] == "admin.event" and m["event"] == name]

    box = Box()
    box.raw = sent
    return box


@pytest.fixture
def user(transactional_db):
    return get_user_model().objects.create_user("operator", password="pass1234!")


@pytest.fixture
def api(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


class Sim:
    """直接调用网关处理上行消息，模拟设备端。"""

    def __init__(self, device_id):
        self.device_id = device_id

    def send(self, **msg):
        return gateway.handle_uplink(self.device_id, msg)

    def register(self, version=None):
        return self.send(type="register", version=version)

    def heartbeat(self):
        return self.send(type="heartbeat")

    def ack(self, cid):
        return self.send(type="ack", command_id=cid)

    def result(self, cid, code=0, data=None):
        return self.send(type="result", command_id=cid, code=code, data=data)

    def progress(self, rid, stage, progress=None, error=None):
        return self.send(type="upgrade_progress", record_id=rid, stage=stage, progress=progress, error=error)


@pytest.fixture
def make_device(transactional_db):
    def _make(device_id, model="GW-100", version="1.0.0", online=False, group=None):
        d = Device.objects.create(device_id=device_id, name=f"设备{device_id}", model=model,
                                  current_version=version, group=group)
        sim = Sim(device_id)
        if online:
            sim.register(version)
        return d, sim
    return _make


@pytest.fixture
def firmware_file():
    def _make(content=b"firmware-binary", name="fw.bin"):
        return SimpleUploadedFile(name, content, content_type="application/octet-stream")
    return _make
