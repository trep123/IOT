from django.contrib import admin

from .models import Command, CommandBatch, CommandTemplate


@admin.register(CommandTemplate)
class CommandTemplateAdmin(admin.ModelAdmin):
    list_display = ["template_id", "code", "name", "is_critical", "timeout_seconds", "is_system"]


@admin.register(Command)
class CommandAdmin(admin.ModelAdmin):
    list_display = ["command_id", "device", "template", "status", "batch", "operator_id", "created_at"]
    list_filter = ["status", "template"]


@admin.register(CommandBatch)
class CommandBatchAdmin(admin.ModelAdmin):
    list_display = ["batch_id", "template", "status", "total", "success", "failed", "pending", "created_at"]
