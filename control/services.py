"""设备控制：指令校验、下发、回执、超时、批量控制与关键操作审计。"""
from datetime import timedelta

from django.conf import settings
from django.db.models import Count
from rest_framework.exceptions import ValidationError

from audit.models import OperationLog, record
from core import realtime, timeutil
from core.exceptions import Conflict
from core.versioning import model_matches
from devices.filters import resolve_scope
from devices.models import Device

from .models import OTA_TEMPLATE_CODE, Command, CommandBatch, CommandTemplate

S = Command.Status
OpType = OperationLog.OpType
TargetType = OperationLog.TargetType

_TYPES = {"int": int, "float": (int, float), "str": str, "bool": bool}


# ------------------------------------------------------------------ 参数校验
def validate_schema(schema: dict) -> None:
    if not isinstance(schema, dict):
        raise ValidationError({"param_schema": "参数定义必须是对象。"})
    for name, spec in schema.items():
        if not isinstance(spec, dict) or spec.get("type") not in _TYPES:
            raise ValidationError({"param_schema": f"参数 {name} 的 type 必须是 {list(_TYPES)} 之一。"})


def validate_params(schema: dict, params: dict) -> dict:
    params = params or {}
    if not isinstance(params, dict):
        raise ValidationError({"params": "参数必须是对象。"})
    errors, cleaned = {}, {}
    for name, spec in (schema or {}).items():
        if name not in params:
            if spec.get("required"):
                errors[name] = "必填。"
            elif "default" in spec:
                cleaned[name] = spec["default"]
            continue
        v = params[name]
        t = spec["type"]
        if t != "bool" and isinstance(v, bool) or not isinstance(v, _TYPES[t]):
            errors[name] = f"类型应为 {t}。"
            continue
        if "enum" in spec and v not in spec["enum"]:
            errors[name] = f"取值必须是 {spec['enum']} 之一。"
        elif "min" in spec and v < spec["min"]:
            errors[name] = f"不能小于 {spec['min']}。"
        elif "max" in spec and v > spec["max"]:
            errors[name] = f"不能大于 {spec['max']}。"
        else:
            cleaned[name] = v
    unknown = set(params) - set(schema or {})
    for name in unknown:
        errors[name] = "未定义的参数。"
    if errors:
        raise ValidationError({"params": errors})
    return cleaned


# ------------------------------------------------------------------ 下发与回执
def command_brief(cmd: Command) -> dict:
    return {"command_id": cmd.command_id, "batch_id": cmd.batch_id, "device_id": cmd.device_id,
            "template_code": cmd.template.code, "status": cmd.status, "result_code": cmd.result_code,
            "error_msg": cmd.error_msg}


def dispatch(cmd: Command, now=None) -> None:
    now = now or timeutil.now()
    cmd.status = S.SENT
    cmd.sent_at = now
    cmd.save(update_fields=["status", "sent_at"])
    realtime.send_to_device(cmd.device_id, {
        "type": "command",
        "command_id": cmd.command_id,
        "code": cmd.template.code,
        "params": cmd.params,
        "timeout": cmd.template.timeout_seconds,
    })
    realtime.broadcast("command_update", command_brief(cmd))


def finalize(cmd: Command, status: str, now=None, code=None, data=None, error="") -> None:
    """指令进入终态，并联动批次统计、关键操作审计、升级记录。"""
    if cmd.is_terminal:
        return
    now = now or timeutil.now()
    cmd.status = status
    cmd.finished_at = now
    cmd.result_code = code
    cmd.result_data = data
    cmd.error_msg = (error or "")[:255]
    cmd.save(update_fields=["status", "finished_at", "result_code", "result_data", "error_msg"])
    realtime.broadcast("command_update", command_brief(cmd))

    if cmd.template.is_critical and status != S.CANCELLED:
        record(cmd.operator_id, OpType.CRITICAL_COMMAND_RESULT, TargetType.COMMAND, cmd.command_id,
               {"device_id": cmd.device_id, "code": cmd.template.code, "status": status,
                "result_code": code, "error": cmd.error_msg}, result=status)
    if cmd.template.code == OTA_TEMPLATE_CODE:
        from firmware import services as firmware
        firmware.on_ota_command_final(cmd, now)
    if cmd.batch_id:
        batch = CommandBatch.objects.select_for_update().get(pk=cmd.batch_id)
        pump_batch(batch, now)


def handle_ack(device: Device, command_id, now=None) -> None:
    cmd = Command.objects.select_related("template").filter(pk=command_id, device=device).first()
    if cmd and cmd.status == S.SENT:
        cmd.status = S.DELIVERED
        cmd.delivered_at = now or timeutil.now()
        cmd.save(update_fields=["status", "delivered_at"])
        realtime.broadcast("command_update", command_brief(cmd))


def handle_result(device: Device, command_id, code, data, message=None, now=None) -> None:
    cmd = Command.objects.select_related("template").filter(pk=command_id, device=device).first()
    if cmd is None or cmd.is_terminal:
        return
    try:
        code = int(code)
    except (TypeError, ValueError):
        code = -1
    if cmd.delivered_at is None:
        cmd.delivered_at = now or timeutil.now()
        cmd.save(update_fields=["delivered_at"])
    finalize(cmd, S.SUCCESS if code == 0 else S.FAILED, now, code=code,
             data=data if isinstance(data, (dict, list)) else ({"value": data} if data is not None else None),
             error="" if code == 0 else (message or f"设备返回错误码 {code}"))


# ------------------------------------------------------------------ 单设备控制
def _check_template(device: Device, template: CommandTemplate) -> None:
    if template.is_system:
        raise ValidationError({"template_id": "系统内置指令不能手工下发。"})
    if not model_matches(template.applicable_models, device.model):
        raise ValidationError({"template_id": f"指令不适用于型号 {device.model}。"})


def create_command(device: Device, template: CommandTemplate, params: dict, operator: str,
                   confirm: bool = False, offline_policy: str = CommandBatch.OfflinePolicy.REJECT, now=None) -> Command:
    now = now or timeutil.now()
    _check_template(device, template)
    params = validate_params(template.param_schema, params)
    if template.is_critical and not confirm:
        raise ValidationError({"confirm": "关键操作需要二次确认（confirm=true）。"})
    if not device.is_online and offline_policy != CommandBatch.OfflinePolicy.QUEUE:
        raise Conflict("设备离线，指令未下发。可选择排队（offline_policy=QUEUE），设备上线后自动下发。")

    cmd = Command.objects.create(device=device, template=template, params=params, operator_id=operator,
                                 created_at=now)
    if template.is_critical:
        record(operator, OpType.CRITICAL_COMMAND, TargetType.DEVICE, device.device_id,
               {"command_id": cmd.command_id, "code": template.code, "params": params,
                "queued": not device.is_online})
    if device.is_online:
        dispatch(cmd, now)
    else:
        realtime.broadcast("command_update", command_brief(cmd))
    return cmd


def ota_template() -> CommandTemplate:
    tpl, _ = CommandTemplate.objects.get_or_create(
        code=OTA_TEMPLATE_CODE,
        defaults={"name": "系统升级通知", "applicable_models": ["*"], "is_system": True,
                  "timeout_seconds": 60, "description": "版本管理复用控制通道下发升级通知"},
    )
    return tpl


def create_system_command(device: Device, params: dict, operator: str, now=None) -> Command:
    """升级通知：一条特殊控制指令，复用下发与回执机制。"""
    cmd = Command.objects.create(device=device, template=ota_template(), params=params,
                                 operator_id=operator, created_at=now or timeutil.now())
    dispatch(cmd, now)
    return cmd


def on_device_online(device: Device, now=None) -> None:
    for cmd in Command.objects.select_related("template").filter(device=device, status=S.PENDING,
                                                                 batch__isnull=True).order_by("command_id"):
        dispatch(cmd, now)
    batch_ids = (Command.objects.filter(device=device, status=S.PENDING, batch__status=CommandBatch.Status.RUNNING)
                 .values_list("batch_id", flat=True).distinct())
    for batch in CommandBatch.objects.select_for_update().filter(pk__in=list(batch_ids)):
        pump_batch(batch, now)


# ------------------------------------------------------------------ 批量控制
def refresh_batch(batch: CommandBatch, now=None) -> None:
    counts = dict(batch.commands.values_list("status").annotate(c=Count("pk")))
    batch.total = sum(counts.values())
    batch.success = counts.get(S.SUCCESS, 0)
    batch.failed = counts.get(S.FAILED, 0) + counts.get(S.TIMEOUT, 0)
    batch.cancelled = counts.get(S.CANCELLED, 0)
    batch.pending = counts.get(S.PENDING, 0) + counts.get(S.SENT, 0) + counts.get(S.DELIVERED, 0)
    if batch.pending == 0 and batch.finished_at is None:
        batch.finished_at = now or timeutil.now()
        if batch.status == CommandBatch.Status.RUNNING:
            batch.status = CommandBatch.Status.PARTIAL_FAILED if batch.failed else CommandBatch.Status.COMPLETED
    batch.save(update_fields=["total", "success", "failed", "cancelled", "pending", "status", "finished_at"])
    realtime.broadcast("batch_update", {"batch_id": batch.batch_id, "status": batch.status, "total": batch.total,
                                        "success": batch.success, "failed": batch.failed,
                                        "pending": batch.pending, "cancelled": batch.cancelled})


def pump_batch(batch: CommandBatch, now=None) -> None:
    """按并发上限推进批次：在线设备补位下发，离线设备按策略失败或继续排队。"""
    now = now or timeutil.now()
    if batch.status == CommandBatch.Status.RUNNING:
        inflight = batch.commands.filter(status__in=Command.INFLIGHT).count()
        slots = batch.concurrency - inflight
        for cmd in batch.commands.select_related("device", "template").filter(status=S.PENDING).order_by("command_id"):
            if cmd.device.is_online:
                if slots <= 0:
                    continue
                dispatch(cmd, now)
                slots -= 1
            elif batch.offline_policy == CommandBatch.OfflinePolicy.REJECT:
                cmd.status, cmd.finished_at, cmd.error_msg = S.FAILED, now, "设备离线"
                cmd.save(update_fields=["status", "finished_at", "error_msg"])
    refresh_batch(batch, now)


def pump_running_batches(now=None) -> int:
    n = 0
    for batch in CommandBatch.objects.select_for_update().filter(status=CommandBatch.Status.RUNNING):
        pump_batch(batch, now)
        n += 1
    return n


def create_batch(template: CommandTemplate, params: dict, scope: dict, operator: str, *,
                 offline_policy=CommandBatch.OfflinePolicy.REJECT, concurrency=None, confirm=False,
                 retry_of=None, now=None) -> CommandBatch:
    now = now or timeutil.now()
    if template.is_system:
        raise ValidationError({"template_id": "系统内置指令不能手工下发。"})
    params = validate_params(template.param_schema, params)
    if template.is_critical and not confirm:
        raise ValidationError({"confirm": "关键操作需要二次确认（confirm=true）。"})
    devices = list(resolve_scope(scope).order_by("device_id"))
    if not devices:
        raise ValidationError({"target_scope": "目标范围内没有设备。"})

    batch = CommandBatch.objects.create(
        template=template, params=params, offline_policy=offline_policy,
        concurrency=concurrency or settings.IOT["DEFAULT_BATCH_CONCURRENCY"],
        target_scope={"scope": scope, "device_ids": [d.device_id for d in devices]},
        operator_id=operator, retry_of=retry_of, created_at=now,
    )
    cmds = []
    for d in devices:
        c = Command(batch=batch, device=d, template=template, params=params, operator_id=operator, created_at=now)
        if not model_matches(template.applicable_models, d.model):
            c.status, c.finished_at, c.error_msg = S.FAILED, now, f"型号 {d.model} 不适用"
        cmds.append(c)
    Command.objects.bulk_create(cmds)
    record(operator, OpType.BATCH_CONTROL, TargetType.BATCH, batch.batch_id,
           {"code": template.code, "params": params, "scope": scope, "total": len(cmds),
            "critical": template.is_critical, "offline_policy": offline_policy,
            "retry_of": retry_of.batch_id if retry_of else None})
    pump_batch(batch, now)
    return batch


def cancel_batch(batch: CommandBatch, operator: str, now=None) -> CommandBatch:
    """取消未下发部分；已下发的指令继续等待回执。"""
    if batch.status != CommandBatch.Status.RUNNING:
        raise Conflict("只有执行中的批次可以取消。")
    now = now or timeutil.now()
    n = batch.commands.filter(status=S.PENDING).update(status=S.CANCELLED, finished_at=now, error_msg="批次已取消")
    batch.status = CommandBatch.Status.CANCELLED
    batch.save(update_fields=["status"])
    record(operator, OpType.BATCH_CANCEL, TargetType.BATCH, batch.batch_id, {"cancelled": n})
    refresh_batch(batch, now)
    return batch


def retry_batch(batch: CommandBatch, operator: str, confirm=False, now=None) -> CommandBatch:
    if batch.status == CommandBatch.Status.RUNNING:
        raise Conflict("批次仍在执行中。")
    ids = list(batch.commands.filter(status__in=[S.FAILED, S.TIMEOUT])
               .exclude(error_msg__startswith="型号").values_list("device_id", flat=True))
    if not ids:
        raise Conflict("没有可重试的失败设备。")
    return create_batch(batch.template, batch.params, {"device_ids": ids}, operator,
                        offline_policy=batch.offline_policy, concurrency=batch.concurrency,
                        confirm=confirm, retry_of=batch, now=now)


# ------------------------------------------------------------------ 超时扫描
def scan_timeouts(now=None) -> int:
    now = now or timeutil.now()
    n = 0
    for cmd in Command.objects.select_related("template").filter(status__in=Command.INFLIGHT):
        if cmd.sent_at and cmd.sent_at + timedelta(seconds=cmd.template.timeout_seconds) < now:
            finalize(cmd, S.TIMEOUT, now, error="执行超时，未收到设备回执")
            n += 1
    deadline = now - timedelta(seconds=settings.IOT["QUEUE_TTL"])
    for cmd in Command.objects.select_related("template").filter(status=S.PENDING, created_at__lt=deadline):
        finalize(cmd, S.TIMEOUT, now, error="排队超时，设备长时间未上线")
        n += 1
    return n
