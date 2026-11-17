"""任务调度：心跳超时、指令超时、批次推进、升级任务推进与阶段超时。"""
import logging
import threading
import time

from django.conf import settings
from django.db import close_old_connections, transaction

from . import timeutil

log = logging.getLogger("iot.scheduler")
_started = False


def run_scan(now=None) -> dict:
    from control import services as control
    from devices import services as devices
    from firmware import services as firmware

    now = now or timeutil.now()
    stats = {}
    with transaction.atomic():
        stats["offline"] = devices.scan_heartbeat_timeouts(now)
    with transaction.atomic():
        stats["command_timeout"] = control.scan_timeouts(now)
    with transaction.atomic():
        stats["batches"] = control.pump_running_batches(now)
    with transaction.atomic():
        stats["upgrade"] = firmware.scan(now)
    return stats


def _loop():
    interval = settings.IOT["SCAN_INTERVAL"]
    while True:
        try:
            close_old_connections()
            run_scan()
        except Exception:  # 调度器不能因单次异常退出
            log.exception("scan failed")
        finally:
            close_old_connections()
        time.sleep(interval)


def start_background_scheduler() -> None:
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, name="iot-scheduler", daemon=True).start()
