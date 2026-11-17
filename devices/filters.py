import django_filters

from .models import Device, DeviceStatusLog


class DeviceFilter(django_filters.FilterSet):
    """组合筛选：状态、型号、分组、版本、时间区间。"""
    model = django_filters.CharFilter(field_name="model")
    model__in = django_filters.BaseInFilter(field_name="model")
    group_id = django_filters.NumberFilter(field_name="group_id")
    version = django_filters.CharFilter(field_name="current_version")
    last_online_after = django_filters.IsoDateTimeFilter(field_name="last_online_at", lookup_expr="gte")
    last_online_before = django_filters.IsoDateTimeFilter(field_name="last_online_at", lookup_expr="lte")
    created_after = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")
    device_id__in = django_filters.BaseInFilter(field_name="device_id")

    class Meta:
        model = Device
        fields = ["online_status", "model", "group_id", "version"]


class DeviceStatusLogFilter(django_filters.FilterSet):
    device_id = django_filters.CharFilter(field_name="device_id")
    occurred_after = django_filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="gte")
    occurred_before = django_filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="lte")

    class Meta:
        model = DeviceStatusLog
        fields = ["device_id", "to_status", "reason"]


def resolve_scope(scope: dict):
    """把目标范围（设备列表 / 分组 / 筛选条件）解析为设备查询集，供批量控制与升级任务复用。"""
    from django.http import QueryDict

    qs = Device.objects.all()
    if scope.get("device_ids"):
        return qs.filter(device_id__in=scope["device_ids"])
    if scope.get("group_id"):
        return qs.filter(group_id=scope["group_id"])
    if scope.get("filters"):
        data = QueryDict(mutable=True)
        for k, v in scope["filters"].items():
            data[k] = ",".join(map(str, v)) if isinstance(v, list) else str(v)
        f = DeviceFilter(data=data, queryset=qs)
        if not f.is_valid():
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"target_scope": f.errors})
        return f.qs
    if scope.get("all"):
        return qs
    from rest_framework.exceptions import ValidationError
    raise ValidationError({"target_scope": "需指定 device_ids、group_id、filters 或 all。"})
