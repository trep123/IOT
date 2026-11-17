import django_filters

from .models import DeviceUpgradeRecord, FirmwareVersion, UpgradePackage, UpgradeTask


class FirmwareVersionFilter(django_filters.FilterSet):
    model = django_filters.CharFilter(method="filter_model", label="适用型号")

    class Meta:
        model = FirmwareVersion
        fields = ["status", "version_no"]

    def filter_model(self, qs, name, value):
        ids = [v.pk for v in qs if value in (v.applicable_models or []) or "*" in (v.applicable_models or [])]
        return qs.filter(pk__in=ids)


class UpgradePackageFilter(django_filters.FilterSet):
    class Meta:
        model = UpgradePackage
        fields = ["version_id", "package_type", "verified"]


class UpgradeTaskFilter(django_filters.FilterSet):
    class Meta:
        model = UpgradeTask
        fields = ["status", "task_type", "version_id", "operator_id"]


class UpgradeRecordFilter(django_filters.FilterSet):
    device_id = django_filters.CharFilter(field_name="device_id")

    class Meta:
        model = DeviceUpgradeRecord
        fields = ["task_id", "device_id", "stage", "phase"]
