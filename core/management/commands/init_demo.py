import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from rest_framework.authtoken.models import Token

from control.models import CommandTemplate
from control.services import ota_template
from devices.models import Device, DeviceGroup
from firmware import services as fw
from firmware.models import FirmwareVersion


class Command(BaseCommand):
    help = "初始化演示数据：管理员、分组、设备、指令模板、两个固件版本，为演示设备生成接入 Key 并导出供模拟器使用"

    def add_arguments(self, parser):
        parser.add_argument("--devices", type=int, default=10)
        parser.add_argument("--password", default="admin123")

    @transaction.atomic
    def handle(self, *args, **opts):
        User = get_user_model()
        admin, created = User.objects.get_or_create(username="admin", defaults={"is_staff": True, "is_superuser": True})
        if created:
            admin.set_password(opts["password"])
            admin.save()
        token, _ = Token.objects.get_or_create(user=admin)

        groups = [DeviceGroup.objects.get_or_create(name=n, defaults={"description": d})[0]
                  for n, d in [("一号车间", "产线网关"), ("园区安防", "摄像头")]]
        devices = []
        for i in range(1, opts["devices"] + 1):
            cam = i % 3 == 0
            d, _ = Device.objects.get_or_create(
                device_id=f"dev-{i:03d}",
                defaults={"name": f"{'摄像头' if cam else '网关'}-{i:03d}", "model": "CAM-1" if cam else "GW-100",
                          "group": groups[1] if cam else groups[0], "current_version": "1.0.0"})
            devices.append(d)

        ota_template()
        templates = [
            ("PING", "连通性测试", ["*"], {}, False, 10),
            ("REBOOT", "重启", ["*"], {"delay": {"type": "int", "min": 0, "max": 600, "default": 0}}, True, 60),
            ("FACTORY_RESET", "恢复出厂", ["*"], {}, True, 120),
            ("SET_PARAM", "参数修改", ["*"], {"key": {"type": "str", "required": True},
                                             "value": {"type": "str", "required": True}}, True, 30),
            ("SET_LED", "指示灯亮度", ["GW-100"], {"level": {"type": "int", "required": True, "min": 0, "max": 100}},
             False, 30),
        ]
        for code, name, models, schema, critical, timeout in templates:
            CommandTemplate.objects.get_or_create(code=code, defaults={
                "name": name, "applicable_models": models, "param_schema": schema,
                "is_critical": critical, "timeout_seconds": timeout})

        for no, min_v, notes in [("1.0.0", "", "出厂版本"), ("1.1.0", "1.0.0", "优化心跳与断线重连")]:
            v, created = FirmwareVersion.objects.get_or_create(
                version_no=no, defaults={"applicable_models": ["GW-100", "CAM-1"], "min_upgradable_version": min_v,
                                         "release_notes": notes})
            if created:
                f = ContentFile(f"demo firmware {no}\n".encode() * 1024, name=f"firmware-{no}.bin")
                fw.create_package(v, f, "FULL", "", "", "admin")
                fw.publish_version(v, "admin")

        # 演示环境：为还没有接入 Key 的设备生成 Key（生产环境由管理员在管理端手动生成）
        from devices import services as device_services
        for d in devices:
            if not d.secret:
                device_services.generate_key(d, "init_demo")

        out = Path(settings.DATA_DIR) / "demo_devices.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps([{"device_id": d.device_id, "secret": d.secret, "version": d.current_version}
                                   for d in devices], ensure_ascii=False, indent=2))
        self.stdout.write(self.style.SUCCESS(
            f"管理员 admin / {opts['password'] if created else '（已存在，密码未改）'}\nAPI Token: {token.key}\n"
            f"{len(devices)} 台设备的密钥已写入 {out}"))
