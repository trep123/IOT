from django.db.models import Count
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.utils import csv_response

from .filters import DeviceFilter, DeviceStatusLogFilter
from .models import Device, DeviceGroup, DeviceStatusLog, new_secret
from .serializers import (DeviceCreateSerializer, DeviceGroupSerializer, DeviceSecretSerializer,
                          DeviceSerializer, DeviceStatusLogSerializer)


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
        if self.action in ("secret", "reset_secret"):
            return DeviceSecretSerializer
        if self.action == "status_logs":
            return DeviceStatusLogSerializer
        return DeviceSerializer

    @action(detail=True, methods=["get"], url_path="status-logs")
    def status_logs(self, request, pk=None):
        device = self.get_object()
        qs = DeviceStatusLog.objects.filter(device=device)
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(DeviceStatusLogSerializer(page, many=True).data)

    @action(detail=True, methods=["get"])
    def secret(self, request, pk=None):
        return Response(DeviceSecretSerializer(self.get_object()).data)

    @action(detail=True, methods=["post"], url_path="reset-secret")
    def reset_secret(self, request, pk=None):
        device = self.get_object()
        device.secret = new_secret()
        device.save(update_fields=["secret", "updated_at"])
        return Response(DeviceSecretSerializer(device).data, status=status.HTTP_200_OK)

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
