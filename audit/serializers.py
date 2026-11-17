from rest_framework import serializers

from .models import OperationLog


class OperationLogSerializer(serializers.ModelSerializer):
    op_type_display = serializers.CharField(source="get_op_type_display", read_only=True)

    class Meta:
        model = OperationLog
        fields = ["op_id", "operator_id", "op_type", "op_type_display", "target_type",
                  "target_id", "detail", "result", "op_time"]
