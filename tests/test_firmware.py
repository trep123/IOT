import hashlib

import pytest

from audit.models import OperationLog
from core import timeutil
from core.scheduler import run_scan
from devices.models import Device
from firmware.models import DeviceUpgradeRecord, UpgradeTask

pytestmark = pytest.mark.django_db(transaction=True)


def make_version(api, firmware_file, version_no, min_ver="", publish=True, models=("GW-100",), diff_from=None):
    r = api.post("/api/firmware-versions/", {"version_no": version_no, "applicable_models": list(models),
                                             "min_upgradable_version": min_ver, "release_notes": "说明"},
                 format="json")
    assert r.status_code == 201, r.data
    vid = r.data["version_id"]
    content = f"fw-{version_no}".encode()
    r = api.post("/api/upgrade-packages/", {"version_id": vid, "package_type": "FULL",
                                            "file": firmware_file(content, f"{version_no}.bin"),
                                            "checksum": hashlib.sha256(content).hexdigest()}, format="multipart")
    assert r.status_code == 201, r.data
    if diff_from:
        r = api.post("/api/upgrade-packages/", {"version_id": vid, "package_type": "DIFF", "base_version": diff_from,
                                                "file": firmware_file(b"diff", "d.bin")}, format="multipart")
        assert r.status_code == 201, r.data
    if publish:
        assert api.post(f"/api/firmware-versions/{vid}/publish/").status_code == 200
    return vid


def run_upgrade(sim, outbox, ok=True):
    """设备端：收到升级通知 → 应答 → 下载/校验/安装/重启 → 上报新版本。"""
    msg = outbox.to_device(sim.device_id, "command")[-1]
    assert msg["code"] == "OTA_UPGRADE"
    p = msg["params"]
    sim.ack(msg["command_id"])
    sim.result(msg["command_id"], 0)
    for stage in ("DOWNLOADING", "VERIFYING", "INSTALLING"):
        sim.progress(p["record_id"], stage, 50)
    if not ok:
        sim.progress(p["record_id"], "FAILED", error="安装失败")
        return p
    sim.progress(p["record_id"], "REBOOTING")
    sim.register(p["version_no"])
    return p


def test_package_integrity_and_publish_rules(api, firmware_file):
    r = api.post("/api/firmware-versions/", {"version_no": "2.0.0", "applicable_models": ["GW-100"],
                                             "min_upgradable_version": "3.0.0"}, format="json")
    assert r.status_code == 400 and "min_upgradable_version" in r.data
    r = api.post("/api/firmware-versions/", {"version_no": "2.0.0", "applicable_models": ["GW-100"]}, format="json")
    vid = r.data["version_id"]
    assert api.post(f"/api/firmware-versions/{vid}/publish/").status_code == 409  # 无升级包
    r = api.post("/api/upgrade-packages/", {"version_id": vid, "package_type": "FULL",
                                            "file": firmware_file(b"abc"), "checksum": "0" * 64}, format="multipart")
    assert r.status_code == 400 and "checksum" in r.data
    r = api.post("/api/upgrade-packages/", {"version_id": vid, "package_type": "DIFF",
                                            "file": firmware_file(b"abc")}, format="multipart")
    assert r.status_code == 400 and "base_version" in r.data
    r = api.post("/api/upgrade-packages/", {"version_id": vid, "package_type": "FULL",
                                            "file": firmware_file(b"abc")}, format="multipart")
    assert r.status_code == 201 and r.data["checksum"] == hashlib.sha256(b"abc").hexdigest()
    pid = r.data["package_id"]
    assert api.post(f"/api/upgrade-packages/{pid}/verify/").data["verified"] is True
    r = api.post(f"/api/firmware-versions/{vid}/publish/")
    assert r.data["status"] == "RELEASABLE"
    r = api.patch(f"/api/firmware-versions/{vid}/", {"status": "DRAFT"}, format="json")
    assert r.data["status"] == "RELEASABLE"  # 状态只读
    assert OperationLog.objects.filter(op_type="VERSION_PUBLISH").count() == 1


def test_package_download_requires_auth_or_device_secret(api, firmware_file, make_device):
    vid = make_version(api, firmware_file, "2.0.0")
    pid = api.get("/api/upgrade-packages/", {"version_id": vid}).data["results"][0]["package_id"]
    from rest_framework.test import APIClient
    anon = APIClient()
    assert anon.get(f"/api/upgrade-packages/{pid}/download/").status_code in (401, 403)
    d, _ = make_device("d1")
    r = anon.get(f"/api/upgrade-packages/{pid}/download/", {"device_id": "d1", "secret": d.secret})
    assert r.status_code == 200 and b"".join(r.streaming_content) == b"fw-2.0.0"


def test_gray_then_full_upgrade(api, firmware_file, make_device, outbox):
    sims = {}
    for i in range(1, 5):
        _, sims[f"d{i}"] = make_device(f"d{i}", online=True)
    _, old = make_device("old", version="0.9.0", online=True)
    make_device("cam", model="CAM-1", online=True)
    vid = make_version(api, firmware_file, "1.1.0", min_ver="1.0.0", diff_from="1.0.0")

    r = api.post("/api/upgrade-tasks/", {"version_id": vid, "target_scope": {"all": True}, "gray_ratio": 0.25,
                                         "failure_threshold": 0.5}, format="json")
    assert r.status_code == 201, r.data
    tid = r.data["task_id"]
    reasons = {e["device_id"]: e["reason"] for e in r.data["excluded"]}
    assert set(reasons) == {"old", "cam"} and "最低可升级版本" in reasons["old"]
    assert r.data["stats"]["total"] == 4 and r.data["stats"]["gray"]["total"] == 1

    r = api.post(f"/api/upgrade-tasks/{tid}/start/")
    assert r.data["status"] == "GRAY"
    gray_rec = DeviceUpgradeRecord.objects.get(task_id=tid, phase="GRAY")
    gray_sim = sims[gray_rec.device_id]
    p = run_upgrade(gray_sim, outbox)
    assert p["package"]["type"] == "DIFF"  # 差分包优先
    gray_rec.refresh_from_db()
    assert gray_rec.stage == "SUCCESS" and gray_rec.progress == 100
    assert Device.objects.get(pk=gray_rec.device_id).current_version == "1.1.0"
    assert len(outbox.to_device("d4", "command")) == 0  # 全量设备尚未下发

    r = api.post(f"/api/upgrade-tasks/{tid}/promote/")
    assert r.data["status"] == "FULL"
    for did, sim in sims.items():
        if did != gray_rec.device_id:
            run_upgrade(sim, outbox)
    r = api.get(f"/api/upgrade-tasks/{tid}/")
    assert r.data["status"] == "COMPLETED" and r.data["stats"]["success"] == 4
    assert api.get(f"/api/upgrade-tasks/{tid}/records/").data["count"] == 4
    ops = set(OperationLog.objects.values_list("op_type", flat=True))
    assert {"UPGRADE_CREATE", "UPGRADE_START", "UPGRADE_PROMOTE"} <= ops


def test_offline_device_upgrade_is_suspended_until_online(api, firmware_file, make_device, outbox):
    make_device("d1", online=True)
    _, s2 = make_device("d2")
    vid = make_version(api, firmware_file, "1.1.0")
    r = api.post("/api/upgrade-tasks/", {"version_id": vid, "target_scope": {"device_ids": ["d1", "d2"]},
                                         "gray_ratio": 1, "start": True}, format="json")
    assert r.data["status"] == "FULL"
    assert outbox.to_device("d2") == []
    s2.register("1.0.0")
    run_upgrade(s2, outbox)
    assert DeviceUpgradeRecord.objects.get(device_id="d2").stage == "SUCCESS"


def test_version_confirm_failure(api, firmware_file, make_device, outbox):
    _, s1 = make_device("d1", online=True)
    vid = make_version(api, firmware_file, "1.1.0")
    api.post("/api/upgrade-tasks/", {"version_id": vid, "target_scope": {"device_ids": ["d1"]},
                                     "gray_ratio": 1, "start": True, "failure_threshold": 1}, format="json")
    msg = outbox.to_device("d1", "command")[-1]
    s1.result(msg["command_id"], 0)
    rid = msg["params"]["record_id"]
    s1.progress(rid, "DOWNLOADING")
    s1.progress(rid, "REBOOTING")
    s1.register("1.0.0")  # 重启后仍是旧版本
    rec = DeviceUpgradeRecord.objects.get(pk=rid)
    assert rec.stage == "FAILED" and "版本确认失败" in rec.error_msg


def test_auto_pause_on_failure_threshold_and_resume_retry(api, firmware_file, make_device, outbox):
    sims = {f"d{i}": make_device(f"d{i}", online=True)[1] for i in range(1, 5)}
    vid = make_version(api, firmware_file, "1.1.0")
    r = api.post("/api/upgrade-tasks/", {"version_id": vid, "target_scope": {"all": True}, "gray_ratio": 0.5,
                                         "failure_threshold": 0.4, "start": True}, format="json")
    tid = r.data["task_id"]
    gray = list(DeviceUpgradeRecord.objects.filter(task_id=tid, phase="GRAY").values_list("device_id", flat=True))
    run_upgrade(sims[gray[0]], outbox, ok=False)  # 1/2 = 50% > 40%
    task = UpgradeTask.objects.get(pk=tid)
    assert task.status == "PAUSED" and "自动暂停" in task.pause_reason
    assert api.post(f"/api/upgrade-tasks/{tid}/promote/").status_code == 409
    assert OperationLog.objects.filter(op_type="UPGRADE_AUTO_PAUSE").exists()

    r = api.post(f"/api/upgrade-tasks/{tid}/resume/")
    assert r.data["status"] == "GRAY"
    run_upgrade(sims[gray[1]], outbox)
    r = api.post(f"/api/upgrade-tasks/{tid}/retry-failed/")
    assert r.status_code == 200
    run_upgrade(sims[gray[0]], outbox)
    assert api.get(f"/api/upgrade-tasks/{tid}/").data["stats"]["gray"]["success"] == 2


def test_stage_timeout(api, firmware_file, make_device, outbox):
    _, s1 = make_device("d1", online=True)
    vid = make_version(api, firmware_file, "1.1.0")
    api.post("/api/upgrade-tasks/", {"version_id": vid, "target_scope": {"all": True}, "gray_ratio": 1,
                                     "failure_threshold": 1, "start": True}, format="json")
    msg = outbox.to_device("d1", "command")[-1]
    s1.result(msg["command_id"], 0)
    s1.progress(msg["params"]["record_id"], "DOWNLOADING", 10)
    timeutil.shift(601)
    s1.heartbeat()
    run_scan()
    rec = DeviceUpgradeRecord.objects.get(pk=msg["params"]["record_id"])
    assert rec.stage == "FAILED" and "超时" in rec.error_msg


def test_rollback(api, firmware_file, make_device, outbox):
    sims = {f"d{i}": make_device(f"d{i}", online=True)[1] for i in range(1, 3)}
    v1 = make_version(api, firmware_file, "1.0.5")  # 可用旧版本
    v2 = make_version(api, firmware_file, "1.1.0")
    tid = api.post("/api/upgrade-tasks/", {"version_id": v2, "target_scope": {"all": True}, "gray_ratio": 1,
                                           "start": True}, format="json").data["task_id"]
    for s in sims.values():
        run_upgrade(s, outbox)
    assert UpgradeTask.objects.get(pk=tid).status == "COMPLETED"

    bad = api.post(f"/api/upgrade-tasks/{tid}/rollback/", {"target_version_id": v2}, format="json")
    assert bad.status_code == 400
    r = api.post(f"/api/upgrade-tasks/{tid}/rollback/", {"target_version_id": v1}, format="json")
    assert r.status_code == 201, r.data
    assert r.data["task"]["status"] == "ROLLED_BACK"
    rb = r.data["rollback_task"]
    assert rb["task_type"] == "ROLLBACK" and rb["parent_task_id"] == tid and rb["status"] == "FULL"
    for s in sims.values():
        run_upgrade(s, outbox)
    assert set(Device.objects.values_list("current_version", flat=True)) == {"1.0.5"}
    assert UpgradeTask.objects.get(pk=rb["task_id"]).status == "COMPLETED"
    assert OperationLog.objects.filter(op_type="ROLLBACK").exists()


def test_device_in_open_task_is_excluded(api, firmware_file, make_device):
    make_device("d1", online=True)
    vid = make_version(api, firmware_file, "1.1.0")
    api.post("/api/upgrade-tasks/", {"version_id": vid, "target_scope": {"all": True}}, format="json")
    r = api.post("/api/upgrade-tasks/", {"version_id": vid, "target_scope": {"all": True}}, format="json")
    assert r.status_code == 400 and r.data["excluded"][0]["reason"].startswith("已在其他")
