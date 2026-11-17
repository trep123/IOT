from django.db import transaction
from django.db.models import Count
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.utils import csv_response

from .filters import DeviceFilter, DeviceStatusLogFilter
from audit.models import OperationLog, record

from . import services
from .models import Device, DeviceGroup, DeviceStatusLog
from .serializers import (BatchKeySerializer, DeviceCreateSerializer, DeviceGroupSerializer,
                          DeviceSecretSerializer, DeviceSerializer, DeviceStatusLogSerializer)


class DeviceGroupViewSet(viewsets.ModelViewSet):
    queryset = DeviceGroup.objects.annotate(device_count=Count("devices"))
    serializer_class = DeviceGroupSerializer
    search_fields = ["name"]
    ordering_fields = ["group_id", "name"]


class DeviceViewSet(viewsets.ModelViewSet):
    """设备档案与在线状态。在线状态只由心跳/连接事件维护。"""
    queryset = Device.objects.select_related("group")
    filterset_class = DeviceFilter
    search_fields = ["device_id", "name"]
    ordering_fields = ["device_id", "name", "model", "current_version", "online_status",
                       "last_online_at", "last_heartbeat_at", "created_at"]

    def get_serializer_class(self):
        if self.action == "create":
            return DeviceCreateSerializer
        if self.action in ("secret", "generate_key", "revoke_key"):
            return DeviceSecretSerializer
        if self.action == "generate_keys":
            return BatchKeySerializer
        if self.action == "status_logs":
            return DeviceStatusLogSerializer
        return DeviceSerializer

    @action(detail=True, methods=["get"], url_path="status-logs")
    def status_logs(self, request, pk=None):
        device = self.get_object()
        qs = DeviceStatusLog.objects.filter(device=device)
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(DeviceStatusLogSerializer(page, many=True).data)

    # ---------------- 接入 Key：管理员手动生成，设备凭 Key 签名上线 ----------------
    @action(detail=True, methods=["get"])
    def secret(self, request, pk=None):
        """查看接入 Key（记审计）。未生成时 secret 为 null。"""
        device = self.get_object()
        if device.secret:
            record(request.user.username, OperationLog.OpType.KEY_VIEW, OperationLog.TargetType.DEVICE,
                   device.device_id)
        return Response(DeviceSecretSerializer(device).data)

    @action(detail=True, methods=["post"], url_path="generate-key")
    def generate_key(self, request, pk=None):
        """生成 / 重新生成接入 Key：旧 Key 立即失效并断开当前连接。"""
        with transaction.atomic():
            device = Device.objects.select_for_update().get(pk=self.get_object().pk)
            services.generate_key(device, request.user.username)
        return Response(DeviceSecretSerializer(device).data)

    @action(detail=True, methods=["post"], url_path="revoke-key")
    def revoke_key(self, request, pk=None):
        """吊销接入 Key：设备立即下线，重新生成前无法上线。"""
        with transaction.atomic():
            device = Device.objects.select_for_update().get(pk=self.get_object().pk)
            services.revoke_key(device, request.user.username)
        return Response(DeviceSecretSerializer(device).data)

    @action(detail=False, methods=["post"], url_path="generate-keys")
    def generate_keys(self, request):
        """批量生成接入 Key（量产烧录）。默认跳过已有 Key 的设备，overwrite=true 时重新生成。"""
        ser = BatchKeySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ids = list(dict.fromkeys(ser.validated_data["device_ids"]))
        generated, skipped = [], []
        with transaction.atomic():
            devices = {d.device_id: d for d in Device.objects.select_for_update().filter(device_id__in=ids)}
            for did in ids:
                d = devices.get(did)
                if d is None:
                    skipped.append({"device_id": did, "reason": "设备不存在"})
                elif d.secret and not ser.validated_data["overwrite"]:
                    skipped.append({"device_id": did, "reason": "已有 Key"})
                else:
                    services.generate_key(d, request.user.username)
                    generated.append({"device_id": did, "name": d.name, "secret": d.secret})
        return Response({"generated": generated, "skipped": skipped})

    @action(detail=False, methods=["get"])
    def summary(self, request):
        qs = self.filter_queryset(self.get_queryset())
        by_status = dict(qs.values_list("online_status").annotate(c=Count("pk")))
        return Response({
            "total": qs.count(),
            "online": by_status.get(Device.OnlineStatus.ONLINE, 0),
            "offline": by_status.get(Device.OnlineStatus.OFFLINE, 0),
            "by_model": list(qs.values("model").annotate(count=Count("pk")).order_by("model")),
            "by_version": list(qs.values("current_version").annotate(count=Count("pk")).order_by("current_version")),
        })

    @action(detail=False, methods=["get"])
    def export(self, request):
        qs = self.filter_queryset(self.get_queryset())

        def rows():
            for d in qs.iterator():
                yield [d.device_id, d.name, d.model, d.group.name if d.group else "", d.current_version,
                       d.get_online_status_display(),
                       d.last_online_at.isoformat() if d.last_online_at else "",
                       d.last_heartbeat_at.isoformat() if d.last_heartbeat_at else ""]
        return csv_response("devices.csv", ["设备编号", "名称", "型号", "分组", "当前版本", "在线状态",
                                            "最近上线", "最近心跳"], rows())


class DeviceStatusLogViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = DeviceStatusLog.objects.select_related("device")
    serializer_class = DeviceStatusLogSerializer
    filterset_class = DeviceStatusLogFilter
    ordering_fields = ["occurred_at", "log_id"]

    @action(detail=False, methods=["get"])
    def export(self, request):
        qs = self.filter_queryset(self.get_queryset())
        rows = ([s.log_id, s.device_id, s.from_status, s.to_status, s.get_reason_display(),
                 s.duration_seconds if s.duration_seconds is not None else "", s.occurred_at.isoformat()]
                for s in qs.iterator())
        return csv_response("status_logs.csv", ["编号", "设备", "变更前", "变更后", "原因", "持续时长(秒)", "时间"], rows)
