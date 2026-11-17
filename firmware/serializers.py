from rest_framework import serializers

from core.versioning import vtuple

from . import services
from .models import DeviceUpgradeRecord, FirmwareVersion, UpgradePackage, UpgradeTask


class UpgradePackageSerializer(serializers.ModelSerializer):
    version_id = serializers.PrimaryKeyRelatedField(source="version", queryset=FirmwareVersion.objects.all())
    version_no = serializers.CharField(source="version.version_no", read_only=True)
    file = serializers.FileField(write_only=True)
    checksum = serializers.CharField(required=False, allow_blank=True, max_length=64,
                                     help_text="可选：客户端计算的 SHA-256，用于完整性校验")
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = UpgradePackage
        fields = ["package_id", "version_id", "version_no", "package_type", "base_version", "file", "file_name",
                  "size", "checksum", "signature", "verified", "download_url", "created_at"]
        read_only_fields = ["package_id", "file_name", "size", "signature", "verified", "created_at"]

    def get_download_url(self, obj):
        request = self.context.get("request")
        url = f"/api/upgrade-packages/{obj.package_id}/download/"
        return request.build_absolute_uri(url) if request else url

    def create(self, v):
        return services.create_package(v["version"], v["file"], v["package_type"], v.get("base_version", ""),
                                       v.get("checksum", ""), self.context["operator"])


class FirmwareVersionSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    packages = serializers.SerializerMethodField()

    class Meta:
        model = FirmwareVersion
        fields = ["version_id", "version_no", "applicable_models", "min_upgradable_version", "release_notes",
                  "status", "status_display", "packages", "created_at", "updated_at"]
        # 状态只能通过 publish / deprecate 动作变更
        read_only_fields = ["version_id", "status", "created_at", "updated_at"]

    def get_packages(self, obj):
        return [{"package_id": p.package_id, "package_type": p.package_type, "base_version": p.base_version,
                 "size": p.size, "verified": p.verified} for p in obj.packages.all()]

    def validate_version_no(self, value):
        if not vtuple(value):
            raise serializers.ValidationError("版本号格式不正确。")
        if self.instance and self.instance.version_no != value and self.instance.status != FirmwareVersion.Status.DRAFT:
            raise serializers.ValidationError("非草稿版本不能修改版本号。")
        return value

    def validate_applicable_models(self, value):
        if not isinstance(value, list) or not value or not all(isinstance(m, str) and m for m in value):
            raise serializers.ValidationError("至少指定一个适用型号。")
        return value

    def validate(self, attrs):
        v = attrs.get("version_no", getattr(self.instance, "version_no", None))
        m = attrs.get("min_upgradable_version", getattr(self.instance, "min_upgradable_version", ""))
        if m and vtuple(m) >= vtuple(v):
            raise serializers.ValidationError({"min_upgradable_version": "最低可升级版本必须低于本版本。"})
        return attrs


class UpgradeRecordSerializer(serializers.ModelSerializer):
    device_id = serializers.CharField(source="device.device_id", read_only=True)
    device_name = serializers.CharField(source="device.name", read_only=True)
    package_id = serializers.IntegerField(source="package.package_id", read_only=True, default=None)
    stage_display = serializers.CharField(source="get_stage_display", read_only=True)

    class Meta:
        model = DeviceUpgradeRecord
        fields = ["record_id", "task_id", "device_id", "device_name", "from_version", "to_version", "package_id",
                  "phase", "command_id", "stage", "stage_display", "progress", "error_msg", "retry_count",
                  "stage_changed_at", "updated_at"]
        read_only_fields = fields


class UpgradeTaskSerializer(serializers.ModelSerializer):
    version_no = serializers.CharField(source="version.version_no", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    parent_task_id = serializers.IntegerField(source="parent_task.task_id", read_only=True, default=None)
    stats = serializers.SerializerMethodField()

    class Meta:
        model = UpgradeTask
        fields = ["task_id", "version_id", "version_no", "task_type", "parent_task_id", "target_scope",
                  "gray_ratio", "gray_device_ids", "failure_threshold", "status", "status_display",
                  "pause_reason", "excluded", "stats", "operator_id", "created_at", "updated_at", "finished_at"]
        read_only_fields = fields

    def get_stats(self, obj):
        return services.task_stats(obj)


class UpgradeTaskCreateSerializer(serializers.Serializer):
    version_id = serializers.PrimaryKeyRelatedField(queryset=FirmwareVersion.objects.all())
    target_scope = serializers.DictField()
    gray_ratio = serializers.FloatField(min_value=0.0001, max_value=1.0, default=0.1)
    gray_device_ids = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    failure_threshold = serializers.FloatField(min_value=0.0, max_value=1.0, default=0.2)
    start = serializers.BooleanField(default=False, help_text="创建后立即开始灰度")

    def validate_target_scope(self, value):
        if not set(value) & {"device_ids", "group_id", "filters", "all"}:
            raise serializers.ValidationError("需指定 device_ids、group_id、filters 或 all 之一。")
        return value

    def create(self, v):
        op = self.context["operator"]
        task = services.create_task(v["version_id"], v["target_scope"], op, gray_ratio=v["gray_ratio"],
                                    gray_device_ids=v["gray_device_ids"], failure_threshold=v["failure_threshold"])
        if v["start"]:
            services.start_task(task, op)
        return task

    def to_representation(self, instance):
        return UpgradeTaskSerializer(instance, context=self.context).data


class PauseSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=200)


class RollbackSerializer(serializers.Serializer):
    target_version_id = serializers.PrimaryKeyRelatedField(queryset=FirmwareVersion.objects.all())
    gray_ratio = serializers.FloatField(min_value=0.0001, max_value=1.0, default=1.0)
    failure_threshold = serializers.FloatField(min_value=0.0, max_value=1.0, required=False)
