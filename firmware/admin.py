from django.contrib import admin

from .models import DeviceUpgradeRecord, FirmwareVersion, UpgradePackage, UpgradeTask


@admin.register(FirmwareVersion)
class FirmwareVersionAdmin(admin.ModelAdmin):
    list_display = ["version_id", "version_no", "status", "min_upgradable_version", "created_at"]


@admin.register(UpgradePackage)
class UpgradePackageAdmin(admin.ModelAdmin):
    list_display = ["package_id", "version", "package_type", "base_version", "size", "verified"]


@admin.register(UpgradeTask)
class UpgradeTaskAdmin(admin.ModelAdmin):
    list_display = ["task_id", "version", "task_type", "status", "gray_ratio", "failure_threshold", "created_at"]


@admin.register(DeviceUpgradeRecord)
class DeviceUpgradeRecordAdmin(admin.ModelAdmin):
    list_display = ["record_id", "task", "device", "from_version", "to_version", "stage", "progress"]
    list_filter = ["stage", "phase"]
