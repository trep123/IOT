from rest_framework import serializers

from .models import Device, DeviceGroup, DeviceStatusLog


class DeviceGroupSerializer(serializers.ModelSerializer):
    device_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = DeviceGroup
        fields = ["group_id", "name", "description", "device_count", "created_at"]
        read_only_fields = ["group_id", "created_at"]


class DeviceSerializer(serializers.ModelSerializer):
    group_id = serializers.PrimaryKeyRelatedField(source="group", queryset=DeviceGroup.objects.all(),
                                                  allow_null=True, required=False)
    group_name = serializers.CharField(source="group.name", read_only=True, default=None)
    online_status_display = serializers.CharField(source="get_online_status_display", read_only=True)

    class Meta:
        model = Device
        fields = ["device_id", "name", "model", "group_id", "group_name", "current_version",
                  "online_status", "online_status_display", "last_heartbeat_at", "last_online_at",
                  "last_offline_at", "created_at", "updated_at"]
        # 在线状态与时间由心跳/连接事件维护，不允许手工修改
        read_only_fields = ["online_status", "last_heartbeat_at", "last_online_at", "last_offline_at",
                            "created_at", "updated_at"]

    def validate(self, attrs):
        if self.instance is not None and "device_id" in attrs and attrs["device_id"] != self.instance.device_id:
            raise serializers.ValidationError({"device_id": "设备编号创建后不可修改。"})
        return attrs


class DeviceCreateSerializer(DeviceSerializer):
    """创建时返回一次设备接入密钥。"""
    secret = serializers.CharField(read_only=True)

    class Meta(DeviceSerializer.Meta):
        fields = DeviceSerializer.Meta.fields + ["secret"]


class DeviceSecretSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = ["device_id", "secret"]


class DeviceStatusLogSerializer(serializers.ModelSerializer):
    device_id = serializers.CharField(source="device.device_id", read_only=True)
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)

    class Meta:
        model = DeviceStatusLog
        fields = ["log_id", "device_id", "from_status", "to_status", "reason", "reason_display",
                  "duration_seconds", "occurred_at"]
