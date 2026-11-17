"""系统版本管理：升级包校验签名、版本发布、灰度/全量升级、失败率熔断、回滚与升级状态跟踪。"""
import hashlib
import hmac
import math
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q
from rest_framework.exceptions import ValidationError

from audit.models import OperationLog, record
from core import realtime, timeutil
from core.exceptions import Conflict
from core.versioning import compare, model_matches
from devices.filters import resolve_scope
from devices.models import Device

from . import storage
from .models import DeviceUpgradeRecord, FirmwareVersion, UpgradePackage, UpgradeTask

OpType = OperationLog.OpType
TargetType = OperationLog.TargetType
Stage = DeviceUpgradeRecord.Stage
TS = UpgradeTask.Status
MAX_NOTIFY_ATTEMPTS = 3


# ================================================================== 升级包
def sign(checksum: str) -> str:
    key = settings.IOT["PACKAGE_SIGN_KEY"].encode()
    return hmac.new(key, checksum.encode(), hashlib.sha256).hexdigest()


def _sha256(fobj) -> tuple[str, int]:
    h, size = hashlib.sha256(), 0
    fobj.seek(0)
    for chunk in iter(lambda: fobj.read(1 << 20), b""):
        h.update(chunk)
        size += len(chunk)
    fobj.seek(0)
    return h.hexdigest(), size


def create_package(version: FirmwareVersion, upload, package_type: str, base_version: str,
                   declared_checksum: str, operator: str) -> UpgradePackage:
    if version.status == FirmwareVersion.Status.DEPRECATED:
        raise Conflict("已废弃的版本不能再上传升级包。")
    if package_type == UpgradePackage.PackageType.DIFF:
        if not base_version:
            raise ValidationError({"base_version": "差分包必须指定起始版本。"})
        if compare(base_version, version.version_no) >= 0:
            raise ValidationError({"base_version": "差分包起始版本必须低于目标版本。"})
    else:
        base_version = ""
    checksum, size = _sha256(upload)
    if declared_checksum and declared_checksum.lower() != checksum:
        raise ValidationError({"checksum": f"完整性校验失败：上传文件 SHA-256 为 {checksum}。"})
    if size == 0:
        raise ValidationError({"file": "升级包为空文件。"})
    pkg = UpgradePackage(version=version, package_type=package_type, base_version=base_version,
                         file_name=upload.name, size=size, checksum=checksum, signature=sign(checksum),
                         verified=True)
    try:
        pkg.file_ref.save(upload.name, upload, save=False)
    except Exception as e:  # noqa: BLE001
        raise Conflict(f"版本文件写入存储失败：{e}")
    pkg.save()
    record(operator, OpType.PACKAGE_UPLOAD, TargetType.PACKAGE, pkg.package_id,
           {"version_no": version.version_no, "type": package_type, "base_version": base_version,
            "size": size, "checksum": checksum, "storage": storage.location(pkg.file_ref.name)})
    return pkg


def delete_package_file(pkg: UpgradePackage) -> None:
    """删除升级包对应的文件 / 对象；存储暂不可用时不阻塞删除记录。"""
    try:
        if pkg.file_ref.name:
            pkg.file_ref.delete(save=False)
    except Exception:  # noqa: BLE001
        pass


def open_package_stream(pkg: UpgradePackage, chunk_size: int = 1 << 20):
    """返回 (可迭代的数据块, 长度)。MinIO 直接流式转发，不落本地临时文件。"""
    if storage.is_minio():
        st = storage.package_storage()
        obj = st.connection.meta.client.get_object(Bucket=st.bucket_name, Key=st._normalize_name(pkg.file_ref.name))
        return obj["Body"].iter_chunks(chunk_size), obj["ContentLength"]
    f = pkg.file_ref.open("rb")

    def gen():
        with f:
            yield from iter(lambda: f.read(chunk_size), b"")
    return gen(), pkg.file_ref.size


def verify_package(pkg: UpgradePackage) -> dict:
    """重新计算文件校验值并验证签名。"""
    try:
        with pkg.file_ref.open("rb") as f:
            checksum, size = _sha256(f)
    except Exception:  # noqa: BLE001  文件缺失或对象存储不可达都视为校验失败
        checksum, size = "", 0
    ok_checksum = checksum == pkg.checksum and size == pkg.size
    ok_signature = hmac.compare_digest(sign(pkg.checksum), pkg.signature)
    pkg.verified = ok_checksum and ok_signature
    pkg.save(update_fields=["verified"])
    return {"package_id": pkg.package_id, "checksum_ok": ok_checksum, "signature_ok": ok_signature,
            "verified": pkg.verified}


def choose_package(version: FirmwareVersion, from_version: str) -> UpgradePackage | None:
    pkgs = version.packages.filter(verified=True)
    diff = pkgs.filter(package_type=UpgradePackage.PackageType.DIFF, base_version=from_version).first()
    return diff or pkgs.filter(package_type=UpgradePackage.PackageType.FULL).first()


# ================================================================== 版本
def publish_version(version: FirmwareVersion, operator: str) -> FirmwareVersion:
    if version.status != FirmwareVersion.Status.DRAFT:
        raise Conflict("只有草稿状态的版本可以置为可发布。")
    if not version.packages.filter(verified=True, package_type=UpgradePackage.PackageType.FULL).exists():
        raise Conflict("版本至少需要一个校验通过的全量升级包。")
    version.status = FirmwareVersion.Status.RELEASABLE
    version.save(update_fields=["status", "updated_at"])
    record(operator, OpType.VERSION_PUBLISH, TargetType.VERSION, version.version_id,
           {"version_no": version.version_no})
    return version


def deprecate_version(version: FirmwareVersion, operator: str) -> FirmwareVersion:
    if version.tasks.filter(status__in=UpgradeTask.OPEN).exists():
        raise Conflict("该版本还有未结束的升级任务。")
    version.status = FirmwareVersion.Status.DEPRECATED
    version.save(update_fields=["status", "updated_at"])
    record(operator, OpType.VERSION_DEPRECATE, TargetType.VERSION, version.version_id,
           {"version_no": version.version_no})
    return version


# ================================================================== 任务统计与推送
def task_stats(task: UpgradeTask) -> dict:
    counts = dict(task.records.values_list("stage").annotate(c=Count("pk")))
    total = sum(counts.values())
    success, failed = counts.get(Stage.SUCCESS, 0), counts.get(Stage.FAILED, 0)
    gray = task.records.filter(phase=DeviceUpgradeRecord.Phase.GRAY).aggregate(
        total=Count("pk"),
        success=Count("pk", filter=Q(stage=Stage.SUCCESS)),
        failed=Count("pk", filter=Q(stage=Stage.FAILED)))
    return {
        "total": total, "success": success, "failed": failed,
        "waiting": counts.get(Stage.WAITING, 0),
        "in_progress": total - success - failed - counts.get(Stage.WAITING, 0),
        "progress": round((success + failed) / total, 4) if total else 0,
        "failure_rate": round(failed / total, 4) if total else 0,
        "by_stage": counts,
        "gray": gray,
    }


def _push_task(task: UpgradeTask) -> None:
    realtime.broadcast("task_update", {"task_id": task.task_id, "status": task.status,
                                       "pause_reason": task.pause_reason, **task_stats(task)})


def _push_record(rec: DeviceUpgradeRecord) -> None:
    realtime.broadcast("upgrade_record", {"record_id": rec.record_id, "task_id": rec.task_id,
                                          "device_id": rec.device_id, "stage": rec.stage,
                                          "progress": rec.progress, "error_msg": rec.error_msg})


def _set_stage(rec: DeviceUpgradeRecord, stage: str, now, progress=None, error=None) -> None:
    rec.stage = stage
    rec.stage_changed_at = now
    if progress is not None:
        rec.progress = max(0, min(100, int(progress)))
    if error is not None:
        rec.error_msg = str(error)[:255]
    rec.save()
    _push_record(rec)


def _active_records(task: UpgradeTask):
    qs = task.records.all()
    if task.status == TS.GRAY:
        qs = qs.filter(phase=DeviceUpgradeRecord.Phase.GRAY)
    return qs


# ================================================================== 创建任务
def create_task(version: FirmwareVersion, scope: dict, operator: str, *, gray_ratio=0.1, gray_device_ids=None,
                failure_threshold=0.2, task_type=UpgradeTask.TaskType.UPGRADE, parent=None,
                devices=None, now=None) -> UpgradeTask:
    now = now or timeutil.now()
    if version.status != FirmwareVersion.Status.RELEASABLE:
        raise Conflict("目标版本不是可发布状态。")
    candidates = list(devices if devices is not None else resolve_scope(scope).order_by("device_id"))
    busy = set(DeviceUpgradeRecord.objects.filter(task__status__in=UpgradeTask.OPEN)
               .exclude(stage__in=DeviceUpgradeRecord.TERMINAL).values_list("device_id", flat=True))
    is_upgrade = task_type == UpgradeTask.TaskType.UPGRADE

    eligible, excluded = [], []
    for d in candidates:
        reason = None
        if not model_matches(version.applicable_models, d.model):
            reason = f"型号 {d.model} 不适用"
        elif d.current_version == version.version_no:
            reason = "已是目标版本"
        elif is_upgrade and version.min_upgradable_version and d.current_version and \
                compare(d.current_version, version.min_upgradable_version) < 0:
            reason = f"当前版本 {d.current_version} 低于最低可升级版本 {version.min_upgradable_version}"
        elif is_upgrade and d.current_version and compare(d.current_version, version.version_no) > 0:
            reason = "当前版本高于目标版本，请使用回滚"
        elif d.device_id in busy:
            reason = "已在其他未完成的升级任务中"
        elif choose_package(version, d.current_version) is None:
            reason = "没有可用的升级包"
        if reason:
            excluded.append({"device_id": d.device_id, "reason": reason})
        else:
            eligible.append(d)
    if not eligible:
        raise ValidationError({"target_scope": "没有符合升级条件的设备。", "excluded": excluded})

    gray_ids = set(gray_device_ids or [])
    if gray_ids:
        gray = {d.device_id for d in eligible if d.device_id in gray_ids}
        if not gray:
            raise ValidationError({"gray_device_ids": "指定的灰度设备都不在可升级范围内。"})
    else:
        n = max(1, math.ceil(len(eligible) * gray_ratio))
        gray = {d.device_id for d in eligible[:n]}

    task = UpgradeTask.objects.create(
        version=version, task_type=task_type, parent_task=parent, operator_id=operator, created_at=now,
        target_scope={"scope": scope, "device_ids": [d.device_id for d in eligible]},
        gray_ratio=gray_ratio, gray_device_ids=sorted(gray_ids), failure_threshold=failure_threshold,
        excluded=excluded)
    DeviceUpgradeRecord.objects.bulk_create([
        DeviceUpgradeRecord(task=task, device=d, from_version=d.current_version, to_version=version.version_no,
                            package=choose_package(version, d.current_version),
                            phase=DeviceUpgradeRecord.Phase.GRAY if d.device_id in gray else DeviceUpgradeRecord.Phase.FULL)
        for d in eligible])
    record(operator, OpType.UPGRADE_CREATE if is_upgrade else OpType.ROLLBACK, TargetType.TASK, task.task_id,
           {"version_no": version.version_no, "task_type": task_type, "eligible": len(eligible),
            "gray": len(gray), "excluded": len(excluded), "parent_task_id": parent.task_id if parent else None})
    _push_task(task)
    return task


# ================================================================== 任务推进
def _notify(rec: DeviceUpgradeRecord, task: UpgradeTask, now) -> None:
    """下发升级通知：复用控制通道的系统指令。"""
    from control import services as control

    pkg = rec.package
    params = {
        "record_id": rec.record_id, "task_id": task.task_id, "task_type": task.task_type,
        "version_no": rec.to_version,
        "package": {
            "package_id": pkg.package_id, "type": pkg.package_type, "base_version": pkg.base_version,
            "size": pkg.size, "checksum": pkg.checksum, "signature": pkg.signature,
            "url": f"{settings.IOT['PUBLIC_BASE_URL'].rstrip('/')}/api/upgrade-packages/{pkg.package_id}/download/",
        },
    }
    cmd = control.create_system_command(rec.device, params, task.operator_id, now)
    rec.command_id = cmd.command_id
    rec.notify_attempts += 1
    rec.stage_changed_at = now
    rec.save(update_fields=["command_id", "notify_attempts", "stage_changed_at", "updated_at"])


def pump_task(task: UpgradeTask, now=None) -> None:
    now = now or timeutil.now()
    if task.status in UpgradeTask.ACTIVE:
        waiting = (_active_records(task).select_related("device", "package")
                   .filter(stage=Stage.WAITING, command_id__isnull=True,
                           device__online_status=Device.OnlineStatus.ONLINE))
        for rec in waiting:
            if rec.package is None or not rec.package.verified:
                _set_stage(rec, Stage.FAILED, now, error="升级包不可用")
                continue
            _notify(rec, task, now)
    evaluate_task(task, now)


def evaluate_task(task: UpgradeTask, now=None) -> None:
    """失败率熔断与完成判定。"""
    now = now or timeutil.now()
    if task.status in UpgradeTask.ACTIVE:
        scope = _active_records(task)
        total = scope.count()
        failed = scope.filter(stage=Stage.FAILED).count()
        rate = (failed - task.failure_baseline) / total if total else 0
        if rate > task.failure_threshold:
            task.paused_from, task.status = task.status, TS.PAUSED
            task.pause_reason = f"失败率 {failed}/{total} 超过阈值 {task.failure_threshold:.0%}，已自动暂停"
            task.save(update_fields=["status", "paused_from", "pause_reason", "updated_at"])
            record("system", OpType.UPGRADE_AUTO_PAUSE, TargetType.TASK, task.task_id,
                   {"failed": failed, "total": total, "threshold": task.failure_threshold}, result="PAUSED")
        elif task.status == TS.FULL and not task.records.exclude(stage__in=DeviceUpgradeRecord.TERMINAL).exists():
            task.status, task.finished_at = TS.COMPLETED, now
            task.save(update_fields=["status", "finished_at", "updated_at"])
    _push_task(task)


def start_task(task: UpgradeTask, operator: str, now=None) -> UpgradeTask:
    if task.status != TS.CREATED:
        raise Conflict("只有已创建的任务可以开始。")
    has_full = task.records.filter(phase=DeviceUpgradeRecord.Phase.FULL).exists()
    task.status = TS.GRAY if has_full else TS.FULL
    task.save(update_fields=["status", "updated_at"])
    record(operator, OpType.UPGRADE_START, TargetType.TASK, task.task_id, {"status": task.status})
    pump_task(task, now)
    return task


def promote_task(task: UpgradeTask, operator: str, now=None) -> UpgradeTask:
    """灰度 → 全量：需操作人确认，且灰度失败率未超阈值。"""
    if task.status != TS.GRAY:
        raise Conflict("只有灰度中的任务可以推进全量。")
    gray = task.records.filter(phase=DeviceUpgradeRecord.Phase.GRAY)
    total, failed = gray.count(), gray.filter(stage=Stage.FAILED).count()
    if total and (failed - task.failure_baseline) / total > task.failure_threshold:
        raise Conflict("灰度失败率超过阈值，不能推进全量。")
    unfinished = gray.exclude(stage__in=DeviceUpgradeRecord.TERMINAL).count()
    task.status = TS.FULL
    task.save(update_fields=["status", "updated_at"])
    record(operator, OpType.UPGRADE_PROMOTE, TargetType.TASK, task.task_id,
           {"gray_total": total, "gray_failed": failed, "gray_unfinished": unfinished})
    pump_task(task, now)
    return task


def pause_task(task: UpgradeTask, operator: str, reason: str = "") -> UpgradeTask:
    if task.status not in UpgradeTask.ACTIVE:
        raise Conflict("只有灰度中或全量中的任务可以暂停。")
    task.paused_from, task.status = task.status, TS.PAUSED
    task.pause_reason = reason or "人工暂停"
    task.save(update_fields=["status", "paused_from", "pause_reason", "updated_at"])
    record(operator, OpType.UPGRADE_PAUSE, TargetType.TASK, task.task_id, {"reason": task.pause_reason})
    _push_task(task)
    return task


def resume_task(task: UpgradeTask, operator: str, now=None) -> UpgradeTask:
    """继续：已发生的失败视为操作人已确认，不再计入熔断阈值。"""
    if task.status != TS.PAUSED:
        raise Conflict("只有已暂停的任务可以继续。")
    task.status = task.paused_from or TS.GRAY
    task.paused_from, task.pause_reason = "", ""
    task.failure_baseline = _active_records(task).filter(stage=Stage.FAILED).count()
    task.save(update_fields=["status", "paused_from", "pause_reason", "failure_baseline", "updated_at"])
    record(operator, OpType.UPGRADE_RESUME, TargetType.TASK, task.task_id, {"status": task.status})
    pump_task(task, now)
    return task


def retry_failed(task: UpgradeTask, operator: str, now=None) -> UpgradeTask:
    if task.status in (TS.CREATED, TS.ROLLED_BACK):
        raise Conflict("当前任务状态不支持重试。")
    failed = task.records.filter(stage=Stage.FAILED)
    n = failed.count()
    if not n:
        raise Conflict("没有失败的设备。")
    for rec in failed.select_related("device"):
        rec.stage, rec.progress, rec.error_msg = Stage.WAITING, 0, ""
        rec.command_id, rec.notify_attempts = None, 0
        rec.retry_count += 1
        rec.from_version = rec.device.current_version
        rec.save()
    if task.status == TS.COMPLETED:
        task.status, task.finished_at = TS.FULL, None
    task.failure_baseline = 0
    task.save(update_fields=["status", "finished_at", "failure_baseline", "updated_at"])
    record(operator, OpType.UPGRADE_RETRY, TargetType.TASK, task.task_id, {"retried": n})
    pump_task(task, now)
    return task


def rollback_task(task: UpgradeTask, target: FirmwareVersion, operator: str, *, gray_ratio=1.0,
                  failure_threshold=None, now=None) -> UpgradeTask | None:
    """暂停原任务，为已升级成功的设备生成 ROLLBACK 任务（流程同升级），原任务标记 ROLLED_BACK。"""
    now = now or timeutil.now()
    if task.task_type != UpgradeTask.TaskType.UPGRADE:
        raise Conflict("回滚任务不能再次回滚。")
    if task.status not in (TS.GRAY, TS.FULL, TS.PAUSED, TS.COMPLETED):
        raise Conflict("当前任务状态不支持回滚。")
    if target.status != FirmwareVersion.Status.RELEASABLE:
        raise ValidationError({"target_version_id": "回滚目标必须是可用（可发布）版本。"})
    if compare(target.version_no, task.version.version_no) >= 0:
        raise ValidationError({"target_version_id": "回滚目标必须是更旧的版本。"})

    if task.status in UpgradeTask.ACTIVE:
        task.paused_from, task.status = task.status, TS.PAUSED
    device_ids = task.records.filter(stage=Stage.SUCCESS).values_list("device_id", flat=True)
    devices = list(Device.objects.filter(device_id__in=list(device_ids),
                                         current_version=task.version.version_no).order_by("device_id"))
    task.records.filter(stage=Stage.WAITING, command_id__isnull=True).update(
        stage=Stage.FAILED, error_msg="任务已回滚，未执行", stage_changed_at=now)
    task.status, task.finished_at = TS.ROLLED_BACK, now
    task.pause_reason = f"已回滚到 {target.version_no}"
    task.save()

    rb = None
    if devices:
        rb = create_task(target, {"rollback_of": task.task_id}, operator, gray_ratio=gray_ratio,
                         failure_threshold=task.failure_threshold if failure_threshold is None else failure_threshold,
                         task_type=UpgradeTask.TaskType.ROLLBACK, parent=task, devices=devices, now=now)
        start_task(rb, operator, now)
    else:
        record(operator, OpType.ROLLBACK, TargetType.TASK, task.task_id,
               {"target_version": target.version_no, "devices": 0})
    _push_task(task)
    return rb


# ================================================================== 设备上报
def handle_progress(device: Device, record_id, stage, progress, error, now=None) -> None:
    now = now or timeutil.now()
    rec = DeviceUpgradeRecord.objects.select_related("task").filter(pk=record_id, device=device).first()
    if rec is None or rec.stage in DeviceUpgradeRecord.TERMINAL:
        return
    if stage == Stage.FAILED:
        _set_stage(rec, Stage.FAILED, now, error=error or "设备上报升级失败")
        evaluate_task(rec.task, now)
        return
    if stage not in DeviceUpgradeRecord.RUNNING:
        return
    # 阶段只能前进（同阶段可更新进度）
    if DeviceUpgradeRecord.ORDER.index(stage) < DeviceUpgradeRecord.ORDER.index(rec.stage):
        return
    if stage == rec.stage:
        rec.progress = max(0, min(100, int(progress or rec.progress)))
        rec.save(update_fields=["progress", "updated_at"])
        _push_record(rec)
    else:
        _set_stage(rec, stage, now, progress=progress if progress is not None else rec.progress)


def on_version_report(device: Device, version: str, now=None) -> None:
    """版本确认：设备重启后上报的版本号等于目标版本即升级成功。"""
    now = now or timeutil.now()
    for rec in (DeviceUpgradeRecord.objects.select_related("task")
                .filter(device=device, stage__in=DeviceUpgradeRecord.RUNNING)):
        if version == rec.to_version:
            _set_stage(rec, Stage.SUCCESS, now, progress=100, error="")
        elif rec.stage == Stage.REBOOTING:
            _set_stage(rec, Stage.FAILED, now, error=f"版本确认失败：设备上报 {version}，期望 {rec.to_version}")
        else:
            continue
        evaluate_task(rec.task, now)


def on_ota_command_final(cmd, now=None) -> None:
    """升级通知指令的回执：设备拒绝 → 记录失败；超时 → 重新挂起，上线/下次调度再发。"""
    now = now or timeutil.now()
    rec = DeviceUpgradeRecord.objects.select_related("task").filter(command_id=cmd.command_id).first()
    if rec is None or rec.stage != Stage.WAITING:
        return
    if cmd.status == cmd.Status.FAILED:
        _set_stage(rec, Stage.FAILED, now, error=f"设备拒绝升级：{cmd.error_msg}")
    elif cmd.status == cmd.Status.TIMEOUT:
        if rec.notify_attempts >= MAX_NOTIFY_ATTEMPTS:
            _set_stage(rec, Stage.FAILED, now, error="升级通知多次超时")
        else:
            rec.command_id = None
            rec.save(update_fields=["command_id", "updated_at"])
    else:
        return
    evaluate_task(rec.task, now)


def on_device_online(device: Device, now=None) -> None:
    """离线挂起的升级在设备上线后继续。"""
    task_ids = (DeviceUpgradeRecord.objects
                .filter(device=device, stage=Stage.WAITING, command_id__isnull=True,
                        task__status__in=UpgradeTask.ACTIVE)
                .values_list("task_id", flat=True).distinct())
    for task in UpgradeTask.objects.select_for_update().filter(pk__in=list(task_ids)):
        pump_task(task, now)


# ================================================================== 调度扫描
def scan(now=None) -> dict:
    now = now or timeutil.now()
    deadline = now - timedelta(seconds=settings.IOT["UPGRADE_STAGE_TIMEOUT"])
    timed_out = 0
    for rec in DeviceUpgradeRecord.objects.select_related("task").filter(
            stage__in=DeviceUpgradeRecord.RUNNING, stage_changed_at__lt=deadline):
        _set_stage(rec, Stage.FAILED, now, error=f"{rec.get_stage_display()}阶段超时")
        timed_out += 1
    tasks = 0
    for task in UpgradeTask.objects.select_for_update().filter(status__in=UpgradeTask.ACTIVE):
        pump_task(task, now)
        tasks += 1
    return {"stage_timeout": timed_out, "tasks": tasks}
