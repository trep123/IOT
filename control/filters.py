import django_filters

from .models import Command, CommandBatch


class CommandFilter(django_filters.FilterSet):
    device_id = django_filters.CharFilter(field_name="device_id")
    template_code = django_filters.CharFilter(field_name="template__code")
    is_critical = django_filters.BooleanFilter(field_name="template__is_critical")
    created_after = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")
    status__in = django_filters.BaseInFilter(field_name="status")

    class Meta:
        model = Command
        fields = ["device_id", "batch_id", "status", "template_id", "operator_id"]


class CommandBatchFilter(django_filters.FilterSet):
    created_after = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = CommandBatch
        fields = ["status", "template_id", "operator_id"]
