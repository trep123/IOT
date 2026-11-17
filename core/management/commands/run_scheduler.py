import time

from django.conf import settings
from django.core.management.base import BaseCommand

from core.scheduler import run_scan


class Command(BaseCommand):
    help = "独立运行任务调度（多进程部署时关闭 IOT_EMBEDDED_SCHEDULER，单独运行本命令）"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="只扫描一次")

    def handle(self, *args, **opts):
        while True:
            stats = run_scan()
            self.stdout.write(str(stats))
            if opts["once"]:
                return
            time.sleep(settings.IOT["SCAN_INTERVAL"])
