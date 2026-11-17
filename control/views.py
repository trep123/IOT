from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.exceptions import Conflict
from core.utils import operator_of

from . import services
from .filters import CommandBatchFilter, CommandFilter
from .models import Command, CommandBatch, CommandTemplate
from .serializers import (CommandBatchCreateSerializer, CommandBatchSerializer, CommandCreateSerializer,
                          CommandSerializer, CommandTemplateSerializer, ConfirmSerializer)


class CommandTemplateViewSet(viewsets.ModelViewSet):
    queryset = CommandTemplate.objects.all()
    serializer_class = CommandTemplateSerializer
    filterset_fields = ["is_critical", "is_system", "code"]
    search_fields = ["code", "name"]

    def perform_update(self, serializer):
        if serializer.instance.is_system:
            raise Conflict("系统内置指令模板不可修改。")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.is_system:
            raise Conflict("系统内置指令模板不可删除。")
        try:
            instance.delete()
        except ProtectedError:
            raise Conflict("模板已有下发记录，不能删除。")


class CommandViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                     viewsets.GenericViewSet):
    """单设备指令：下发（POST）、结果查询。状态流转 PENDING→SENT→DELIVERED→SUCCESS|FAILED|TIMEOUT。"""
    queryset = Command.objects.select_related("template", "device")
    filterset_class = CommandFilter
    ordering_fields = ["command_id", "created_at", "finished_at"]

    def get_serializer_class(self):
        return CommandCreateSerializer if self.action == "create" else CommandSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "operator": operator_of(self.request)}


class CommandBatchViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                          viewsets.GenericViewSet):
    """批量控制：按设备列表/分组/筛选条件生成批次，按并发上限分批下发。"""
    queryset = CommandBatch.objects.select_related("template")
    filterset_class = CommandBatchFilter
    ordering_fields = ["batch_id", "created_at"]

    def get_serializer_class(self):
        if self.action == "create":
            return CommandBatchCreateSerializer
        if self.action == "retry":
            return ConfirmSerializer
        if self.action == "commands":
            return CommandSerializer
        return CommandBatchSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "operator": operator_of(self.request)}

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        batch = CommandBatch.objects.select_for_update().get(pk=self.get_object().pk)
        services.cancel_batch(batch, operator_of(request))
        return Response(CommandBatchSerializer(batch).data)

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        """对失败/超时设备一键重试，生成新批次。"""
        s = ConfirmSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        new_batch = services.retry_batch(self.get_object(), operator_of(request), confirm=s.validated_data["confirm"])
        return Response(CommandBatchSerializer(new_batch).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def commands(self, request, pk=None):
        # 子列表的筛选参数属于指令，不能套用批次自身的筛选器
        batch = get_object_or_404(self.get_queryset(), pk=pk)
        self.check_object_permissions(request, batch)
        qs = CommandFilter(request.query_params, queryset=batch.commands.select_related("template", "device")).qs
        page = self.paginate_queryset(qs.order_by("command_id"))
        return self.get_paginated_response(CommandSerializer(page, many=True).data)
