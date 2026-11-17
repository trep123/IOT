import django_filters

from .models import OperationLog


class OperationLogFilter(django_filters.FilterSet):
    op_time_after = django_filters.IsoDateTimeFilter(field_name="op_time", lookup_expr="gte")
    op_time_before = django_filters.IsoDateTimeFilter(field_name="op_time", lookup_expr="lte")

    class Meta:
        model = OperationLog
        fields = ["operator_id", "op_type", "target_type", "target_id", "result"]
