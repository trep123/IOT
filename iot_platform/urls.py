from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from audit.views import OperationLogViewSet
from control.views import CommandBatchViewSet, CommandTemplateViewSet, CommandViewSet
from devices.views import DeviceGroupViewSet, DeviceStatusLogViewSet, DeviceViewSet
from firmware.views import (DeviceUpgradeRecordViewSet, FirmwareVersionViewSet,
                            UpgradePackageViewSet, UpgradeTaskViewSet)

router = DefaultRouter()
router.register("groups", DeviceGroupViewSet, basename="group")
router.register("devices", DeviceViewSet, basename="device")
router.register("status-logs", DeviceStatusLogViewSet, basename="status-log")
router.register("command-templates", CommandTemplateViewSet, basename="command-template")
router.register("commands", CommandViewSet, basename="command")
router.register("command-batches", CommandBatchViewSet, basename="command-batch")
router.register("firmware-versions", FirmwareVersionViewSet, basename="firmware-version")
router.register("upgrade-packages", UpgradePackageViewSet, basename="upgrade-package")
router.register("upgrade-tasks", UpgradeTaskViewSet, basename="upgrade-task")
router.register("upgrade-records", DeviceUpgradeRecordViewSet, basename="upgrade-record")
router.register("operation-logs", OperationLogViewSet, basename="operation-log")

urlpatterns = [
    path("", TemplateView.as_view(template_name="index.html"), name="console"),
    path("admin/", admin.site.urls),
    path("api/auth/token/", obtain_auth_token, name="api-token"),
    path("api/auth/", include("rest_framework.urls")),
    path("api/", include(router.urls)),
]
