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
    has_key = serializers.BooleanField(read_only=True)
    key_created_at = serializers.DateTimeField(source="secret_created_at", read_only=True)

    class Meta:
        model = Device
        fields = ["device_id", "name", "model", "group_id", "group_name", "current_version",
                  "online_status", "online_status_display", "has_key", "key_created_at",
                  "last_heartbeat_at", "last_online_at", "last_offline_at", "created_at", "updated_at"]
        # 在线状态与时间由心跳/连接事件维护，不允许手工修改
        read_only_fields = ["online_status", "last_heartbeat_at", "last_online_at", "last_offline_at",
                            "created_at", "updated_at"]

    def validate(self, attrs):
        if self.instance is not None and "device_id" in attrs and attrs["device_id"] != self.instance.device_id:
            raise serializers.ValidationError({"device_id": "设备编号创建后不可修改。"})
        return attrs


class DeviceCreateSerializer(DeviceSerializer):
    """建档默认不生成接入 Key；generate_key=true 时同时生成，并在响应中返回一次。"""
    generate_key = serializers.BooleanField(write_only=True, required=False, default=False)
    secret = serializers.CharField(read_only=True, allow_null=True)

    class Meta(DeviceSerializer.Meta):
        fields = DeviceSerializer.Meta.fields + ["generate_key", "secret"]

    def create(self, validated_data):
        generate = validated_data.pop("generate_key", False)
        device = super().create(validated_data)
        if generate:
            from . import services
            request = self.context.get("request")
            services.generate_key(device, operator=getattr(getattr(request, "user", None), "username", "system"))
        return device

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["secret"] = instance.secret or None
        return data


class DeviceSecretSerializer(serializers.ModelSerializer):
    secret = serializers.CharField(allow_null=True)
    key_created_at = serializers.DateTimeField(source="secret_created_at", read_only=True)

    class Meta:
        model = Device
        fields = ["device_id", "secret", "key_created_at"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["secret"] = instance.secret or None
        return data


class BatchKeySerializer(serializers.Serializer):
    device_ids = serializers.ListField(child=serializers.CharField(), allow_empty=False, max_length=1000)
    overwrite = serializers.BooleanField(default=False, help_text="已有 Key 的设备是否重新生成")


class DeviceStatusLogSerializer(serializers.ModelSerializer):
    device_id = serializers.CharField(source="device.device_id", read_only=True)
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)

    class Meta:
        model = DeviceStatusLog
        fields = ["log_id", "device_id", "from_status", "to_status", "reason", "reason_display",
                  "duration_seconds", "occurred_at"]
