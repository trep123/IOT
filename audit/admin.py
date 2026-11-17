from django.contrib import admin

from .models import OperationLog


@admin.register(OperationLog)
class OperationLogAdmin(admin.ModelAdmin):
    list_display = ["op_id", "operator_id", "op_type", "target_type", "target_id", "result", "op_time"]
    list_filter = ["op_type", "target_type", "result"]
