from django.contrib import admin

from .models import Device, DeviceGroup, DeviceStatusLog

admin.site.register(DeviceGroup)


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ["device_id", "name", "model", "group", "current_version", "online_status", "last_heartbeat_at"]
    list_filter = ["online_status", "model", "group"]
    search_fields = ["device_id", "name"]


@admin.register(DeviceStatusLog)
class DeviceStatusLogAdmin(admin.ModelAdmin):
    list_display = ["log_id", "device", "from_status", "to_status", "reason", "duration_seconds", "occurred_at"]
    list_filter = ["reason", "to_status"]
