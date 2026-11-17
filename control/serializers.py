from rest_framework import serializers

from devices.models import Device

from . import services
from .models import Command, CommandBatch, CommandTemplate


class CommandTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommandTemplate
        fields = ["template_id", "code", "name", "applicable_models", "param_schema", "is_critical",
                  "timeout_seconds", "is_system", "description"]
        read_only_fields = ["template_id", "is_system"]

    def validate_param_schema(self, value):
        services.validate_schema(value)
        return value

    def validate_applicable_models(self, value):
        if not isinstance(value, list) or not all(isinstance(m, str) for m in value):
            raise serializers.ValidationError("适用型号必须是字符串数组，[\"*\"] 表示全部。")
        return value or ["*"]

    def validate_timeout_seconds(self, value):
        if value < 1:
            raise serializers.ValidationError("超时时间至少 1 秒。")
        return value


class CommandSerializer(serializers.ModelSerializer):
    device_id = serializers.CharField(source="device.device_id", read_only=True)
    template_id = serializers.IntegerField(source="template.template_id", read_only=True)
    template_code = serializers.CharField(source="template.code", read_only=True)
    template_name = serializers.CharField(source="template.name", read_only=True)
    is_critical = serializers.BooleanField(source="template.is_critical", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Command
        fields = ["command_id", "batch_id", "device_id", "template_id", "template_code", "template_name",
                  "is_critical", "params", "status", "status_display", "result_code", "result_data",
                  "error_msg", "operator_id", "created_at", "sent_at", "delivered_at", "finished_at"]
        read_only_fields = fields


class CommandCreateSerializer(serializers.Serializer):
    """单设备指令下发。"""
    device_id = serializers.PrimaryKeyRelatedField(queryset=Device.objects.all())
    template_id = serializers.PrimaryKeyRelatedField(queryset=CommandTemplate.objects.all())
    params = serializers.DictField(required=False, default=dict)
    confirm = serializers.BooleanField(required=False, default=False, help_text="关键操作二次确认")
    offline_policy = serializers.ChoiceField(choices=CommandBatch.OfflinePolicy.choices,
                                             default=CommandBatch.OfflinePolicy.REJECT)

    def create(self, validated):
        return services.create_command(validated["device_id"], validated["template_id"], validated["params"],
                                       self.context["operator"], confirm=validated["confirm"],
                                       offline_policy=validated["offline_policy"])

    def to_representation(self, instance):
        return CommandSerializer(instance, context=self.context).data


class CommandBatchSerializer(serializers.ModelSerializer):
    template_id = serializers.IntegerField(source="template.template_id", read_only=True)
    template_code = serializers.CharField(source="template.code", read_only=True)
    template_name = serializers.CharField(source="template.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    success_rate = serializers.FloatField(read_only=True)
    retry_of = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = CommandBatch
        fields = ["batch_id", "template_id", "template_code", "template_name", "params", "target_scope",
                  "offline_policy", "concurrency", "total", "success", "failed", "pending", "cancelled",
                  "success_rate", "status", "status_display", "retry_of", "operator_id", "created_at",
                  "finished_at"]
        read_only_fields = fields


class TargetScopeField(serializers.DictField):
    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        keys = {"device_ids", "group_id", "filters", "all"}
        if not value or not set(value) & keys:
            raise serializers.ValidationError("需指定 device_ids、group_id、filters 或 all 之一。")
        if "device_ids" in value and not isinstance(value["device_ids"], list):
            raise serializers.ValidationError("device_ids 必须是数组。")
        if "filters" in value and not isinstance(value["filters"], dict):
            raise serializers.ValidationError("filters 必须是对象。")
        return value


class CommandBatchCreateSerializer(serializers.Serializer):
    template_id = serializers.PrimaryKeyRelatedField(queryset=CommandTemplate.objects.all())
    params = serializers.DictField(required=False, default=dict)
    target_scope = TargetScopeField()
    offline_policy = serializers.ChoiceField(choices=CommandBatch.OfflinePolicy.choices,
                                             default=CommandBatch.OfflinePolicy.REJECT)
    concurrency = serializers.IntegerField(required=False, min_value=1, max_value=1000)
    confirm = serializers.BooleanField(required=False, default=False)

    def create(self, v):
        return services.create_batch(v["template_id"], v["params"], v["target_scope"], self.context["operator"],
                                     offline_policy=v["offline_policy"], concurrency=v.get("concurrency"),
                                     confirm=v["confirm"])

    def to_representation(self, instance):
        return CommandBatchSerializer(instance, context=self.context).data


class ConfirmSerializer(serializers.Serializer):
    confirm = serializers.BooleanField(required=False, default=False)
