from rest_framework import viewsets
from rest_framework.decorators import action

from core.utils import csv_response

from .filters import OperationLogFilter
from .models import OperationLog
from .serializers import OperationLogSerializer


class OperationLogViewSet(viewsets.ReadOnlyModelViewSet):
    """操作审计（只读）。"""
    queryset = OperationLog.objects.all()
    serializer_class = OperationLogSerializer
    filterset_class = OperationLogFilter
    search_fields = ["target_id", "operator_id"]
    ordering_fields = ["op_time", "op_id"]

    @action(detail=False, methods=["get"])
    def export(self, request):
        qs = self.filter_queryset(self.get_queryset())
        rows = ([o.op_id, o.operator_id, o.get_op_type_display(), o.target_type, o.target_id,
                 o.result, o.op_time.isoformat(), o.detail] for o in qs.iterator())
        return csv_response("operation_logs.csv",
                            ["编号", "操作人", "类型", "对象类型", "对象", "结果", "时间", "详情"], rows)
