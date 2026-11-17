import pytest

from audit.models import OperationLog
from control.models import Command, CommandBatch, CommandTemplate
from core import timeutil
from core.scheduler import run_scan

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def reboot(transactional_db):
    return CommandTemplate.objects.create(code="REBOOT", name="重启", applicable_models=["GW-100"],
                                          is_critical=True, timeout_seconds=30)


@pytest.fixture
def set_led(transactional_db):
    return CommandTemplate.objects.create(
        code="SET_LED", name="设置亮度", applicable_models=["*"], timeout_seconds=30,
        param_schema={"level": {"type": "int", "required": True, "min": 0, "max": 100}})


def test_single_command_full_lifecycle(api, make_device, set_led, outbox):
    make_device("d1", online=True)
    r = api.post("/api/commands/", {"device_id": "d1", "template_id": set_led.pk, "params": {"level": 50}},
                 format="json")
    assert r.status_code == 201, r.data
    cid = r.data["command_id"]
    assert r.data["status"] == "SENT"
    msg = outbox.to_device("d1", "command")[-1]
    assert msg == {"type": "command", "command_id": cid, "code": "SET_LED", "params": {"level": 50}, "timeout": 30}

    from tests.conftest import Sim
    sim = Sim("d1")
    sim.ack(cid)
    assert Command.objects.get(pk=cid).status == "DELIVERED"
    sim.result(cid, 0, {"level": 50})
    r = api.get(f"/api/commands/{cid}/")
    assert r.data["status"] == "SUCCESS" and r.data["result_data"] == {"level": 50}


def test_param_validation_and_model_check(api, make_device, set_led, reboot):
    make_device("d1", online=True)
    make_device("c1", model="CAM-1", online=True)
    r = api.post("/api/commands/", {"device_id": "d1", "template_id": set_led.pk, "params": {"level": 101}},
                 format="json")
    assert r.status_code == 400 and "level" in r.data["params"]
    r = api.post("/api/commands/", {"device_id": "d1", "template_id": set_led.pk, "params": {}}, format="json")
    assert r.status_code == 400
    r = api.post("/api/commands/", {"device_id": "c1", "template_id": reboot.pk, "confirm": True}, format="json")
    assert r.status_code == 400 and "template_id" in r.data


def test_critical_command_requires_confirm_and_is_audited(api, make_device, reboot):
    make_device("d1", online=True)
    r = api.post("/api/commands/", {"device_id": "d1", "template_id": reboot.pk}, format="json")
    assert r.status_code == 400 and "confirm" in r.data
    r = api.post("/api/commands/", {"device_id": "d1", "template_id": reboot.pk, "confirm": True}, format="json")
    assert r.status_code == 201
    from tests.conftest import Sim
    Sim("d1").result(r.data["command_id"], 1)
    ops = list(OperationLog.objects.order_by("op_id").values_list("op_type", "result"))
    assert ops == [("CRITICAL_COMMAND", "SUCCESS"), ("CRITICAL_COMMAND_RESULT", "FAILED")]
    assert api.get("/api/operation-logs/", {"op_type": "CRITICAL_COMMAND"}).data["count"] == 1


def test_offline_reject_or_queue(api, make_device, set_led, outbox):
    _, sim = make_device("d1")
    body = {"device_id": "d1", "template_id": set_led.pk, "params": {"level": 1}}
    r = api.post("/api/commands/", body, format="json")
    assert r.status_code == 409
    r = api.post("/api/commands/", {**body, "offline_policy": "QUEUE"}, format="json")
    assert r.status_code == 201 and r.data["status"] == "PENDING"
    assert outbox.to_device("d1") == []
    sim.register("1.0.0")  # 上线后自动下发
    assert Command.objects.get(pk=r.data["command_id"]).status == "SENT"
    assert len(outbox.to_device("d1", "command")) == 1


def test_command_timeout(api, make_device, set_led):
    make_device("d1", online=True)
    r = api.post("/api/commands/", {"device_id": "d1", "template_id": set_led.pk, "params": {"level": 1}},
                 format="json")
    timeutil.shift(31)
    from tests.conftest import Sim
    Sim("d1").heartbeat()
    run_scan()
    assert Command.objects.get(pk=r.data["command_id"]).status == "TIMEOUT"


def test_batch_concurrency_offline_policy_and_retry(api, make_device, set_led, outbox):
    sims = {}
    for i in range(1, 5):
        _, sims[f"d{i}"] = make_device(f"d{i}", online=i != 4)
    r = api.post("/api/command-batches/", {
        "template_id": set_led.pk, "params": {"level": 10},
        "target_scope": {"filters": {"model": "GW-100"}}, "concurrency": 2}, format="json")
    assert r.status_code == 201, r.data
    bid = r.data["batch_id"]
    # 并发上限 2：d1、d2 下发；d4 离线按 REJECT 直接失败；d3 等待补位
    assert r.data["total"] == 4 and r.data["failed"] == 1 and r.data["pending"] == 3
    assert Command.objects.get(batch_id=bid, device_id="d3").status == "PENDING"

    c1 = Command.objects.get(batch_id=bid, device_id="d1").pk
    sims["d1"].result(c1, 0)
    c3 = Command.objects.get(batch_id=bid, device_id="d3")
    assert c3.status == "SENT"  # 补位下发
    sims["d2"].result(Command.objects.get(batch_id=bid, device_id="d2").pk, 0)
    sims["d3"].result(c3.pk, 2)

    b = api.get(f"/api/command-batches/{bid}/").data
    assert (b["status"], b["success"], b["failed"], b["pending"]) == ("PARTIAL_FAILED", 2, 2, 0)
    assert b["success_rate"] == 0.5
    assert api.get(f"/api/command-batches/{bid}/commands/", {"status": "FAILED"}).data["count"] == 2

    r = api.post(f"/api/command-batches/{bid}/retry/", {}, format="json")
    assert r.status_code == 201
    assert sorted(r.data["target_scope"]["device_ids"]) == ["d3", "d4"]
    assert r.data["retry_of"] == bid
    assert OperationLog.objects.filter(op_type="BATCH_CONTROL").count() == 2


def test_batch_queue_and_cancel(api, make_device, set_led):
    make_device("d1", online=True)
    _, s2 = make_device("d2")
    r = api.post("/api/command-batches/", {
        "template_id": set_led.pk, "params": {"level": 1}, "target_scope": {"device_ids": ["d1", "d2"]},
        "offline_policy": "QUEUE"}, format="json")
    bid = r.data["batch_id"]
    assert r.data["pending"] == 2 and r.data["failed"] == 0
    r = api.post(f"/api/command-batches/{bid}/cancel/")
    assert r.status_code == 200 and r.data["status"] == "CANCELLED" and r.data["cancelled"] == 1
    s2.register("1.0.0")
    assert Command.objects.get(batch_id=bid, device_id="d2").status == "CANCELLED"
    assert api.post(f"/api/command-batches/{bid}/cancel/").status_code == 409
    assert CommandBatch.objects.get(pk=bid).pending == 1  # d1 已下发，继续等待回执
