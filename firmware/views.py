from urllib.parse import quote

from django.db.models.deletion import ProtectedError
from django.http import Http404, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from core.exceptions import Conflict
from core.utils import operator_of

from . import services
from .filters import FirmwareVersionFilter, UpgradePackageFilter, UpgradeRecordFilter, UpgradeTaskFilter
from .models import DeviceUpgradeRecord, FirmwareVersion, UpgradePackage, UpgradeTask
from .permissions import IsAuthenticatedOrDevice
from .serializers import (FirmwareVersionSerializer, PauseSerializer, RollbackSerializer,
                          UpgradePackageSerializer, UpgradeRecordSerializer, UpgradeTaskCreateSerializer,
                          UpgradeTaskSerializer)


class OperatorContextMixin:
    def get_serializer_context(self):
        return {**super().get_serializer_context(), "operator": operator_of(self.request)}


class FirmwareVersionViewSet(OperatorContextMixin, viewsets.ModelViewSet):
    """版本信息维护；状态通过 publish / deprecate 动作流转（DRAFT → RELEASABLE → DEPRECATED）。"""
    queryset = FirmwareVersion.objects.prefetch_related("packages")
    serializer_class = FirmwareVersionSerializer
    filterset_class = FirmwareVersionFilter
    search_fields = ["version_no", "release_notes"]
    ordering_fields = ["version_id", "version_no", "created_at"]

    def perform_destroy(self, instance):
        if instance.status != FirmwareVersion.Status.DRAFT:
            raise Conflict("只有草稿版本可以删除。")
        pkgs = list(instance.packages.all())
        try:
            instance.delete()
        except ProtectedError:
            raise Conflict("版本已被升级任务引用，不能删除。")
        for pkg in pkgs:
            services.delete_package_file(pkg)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        version = services.publish_version(self.get_object(), operator_of(request))
        return Response(self.get_serializer(version).data)

    @action(detail=True, methods=["post"])
    def deprecate(self, request, pk=None):
        version = services.deprecate_version(self.get_object(), operator_of(request))
        return Response(self.get_serializer(version).data)


class UpgradePackageViewSet(OperatorContextMixin, mixins.CreateModelMixin, mixins.ListModelMixin,
                            mixins.RetrieveModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """升级包：multipart 上传后自动计算 SHA-256 并签名。"""
    queryset = UpgradePackage.objects.select_related("version")
    serializer_class = UpgradePackageSerializer
    filterset_class = UpgradePackageFilter
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.action == "download":
            return [IsAuthenticatedOrDevice()]
        return super().get_permissions()

    def perform_destroy(self, instance):
        if instance.version.status != FirmwareVersion.Status.DRAFT:
            raise Conflict("只有草稿版本的升级包可以删除。")
        services.delete_package_file(instance)
        instance.delete()

    @action(detail=False, methods=["get"])
    def storage(self, request):
        """版本文件存储状态：后端（本地 / MinIO）、存储桶、连通性、文件数与总大小。"""
        from django.db.models import Count, Sum

        from .storage import status as storage_status
        agg = UpgradePackage.objects.aggregate(count=Count("package_id"), total_size=Sum("size"))
        return Response({**storage_status(), "package_count": agg["count"], "total_size": agg["total_size"] or 0})

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        return Response(services.verify_package(self.get_object()))

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        pkg = self.get_object()
        try:
            chunks, length = services.open_package_stream(pkg)
        except Exception:  # noqa: BLE001
            raise Http404("版本文件不存在或存储不可用。")
        resp = StreamingHttpResponse(chunks, content_type="application/octet-stream")
        resp["Content-Length"] = str(length)
        resp["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(pkg.file_name)}"
        resp["X-Checksum-Sha256"] = pkg.checksum
        resp["X-Signature"] = pkg.signature
        return resp


class UpgradeTaskViewSet(OperatorContextMixin, mixins.CreateModelMixin, mixins.ListModelMixin,
                         mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """升级任务：CREATED → GRAY → FULL → COMPLETED；GRAY/FULL → PAUSED → 继续 | ROLLED_BACK。"""
    queryset = UpgradeTask.objects.select_related("version", "parent_task")
    filterset_class = UpgradeTaskFilter
    ordering_fields = ["task_id", "created_at"]

    def get_serializer_class(self):
        return {"create": UpgradeTaskCreateSerializer, "pause": PauseSerializer,
                "rollback": RollbackSerializer, "records": UpgradeRecordSerializer}.get(self.action, UpgradeTaskSerializer)

    def _locked(self):
        return UpgradeTask.objects.select_for_update().get(pk=self.get_object().pk)

    def _ok(self, task, code=status.HTTP_200_OK):
        task.refresh_from_db()
        return Response(UpgradeTaskSerializer(task, context=self.get_serializer_context()).data, status=code)

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        return self._ok(services.start_task(self._locked(), operator_of(request)))

    @action(detail=True, methods=["post"])
    def promote(self, request, pk=None):
        """灰度 → 全量（操作人确认）。"""
        return self._ok(services.promote_task(self._locked(), operator_of(request)))

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        s = PauseSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return self._ok(services.pause_task(self._locked(), operator_of(request), s.validated_data["reason"]))

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        return self._ok(services.resume_task(self._locked(), operator_of(request)))

    @action(detail=True, methods=["post"], url_path="retry-failed")
    def retry_failed(self, request, pk=None):
        return self._ok(services.retry_failed(self._locked(), operator_of(request)))

    @action(detail=True, methods=["post"])
    def rollback(self, request, pk=None):
        s = RollbackSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        task = self._locked()
        rb = services.rollback_task(task, v["target_version_id"], operator_of(request),
                                    gray_ratio=v["gray_ratio"], failure_threshold=v.get("failure_threshold"))
        ctx = self.get_serializer_context()
        task.refresh_from_db()
        return Response({"task": UpgradeTaskSerializer(task, context=ctx).data,
                         "rollback_task": UpgradeTaskSerializer(rb, context=ctx).data if rb else None},
                        status=status.HTTP_201_CREATED if rb else status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def records(self, request, pk=None):
        task = get_object_or_404(self.get_queryset(), pk=pk)
        self.check_object_permissions(request, task)
        qs = UpgradeRecordFilter(request.query_params, queryset=task.records.select_related("device", "package")).qs
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(UpgradeRecordSerializer(page, many=True).data)


class DeviceUpgradeRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """逐台升级记录：下载 → 校验 → 安装 → 重启 → 版本确认。"""
    queryset = DeviceUpgradeRecord.objects.select_related("device", "package")
    serializer_class = UpgradeRecordSerializer
    filterset_class = UpgradeRecordFilter
    ordering_fields = ["record_id", "updated_at"]
