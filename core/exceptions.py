from rest_framework.exceptions import APIException


class Conflict(APIException):
    """状态冲突，例如设备离线、任务状态不允许当前操作。"""
    status_code = 409
    default_detail = "当前状态不允许该操作。"
    default_code = "conflict"
