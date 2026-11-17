"""统一时间源。测试中可通过 shift() 平移时钟模拟超时。"""
from datetime import timedelta

from django.utils import timezone

_offset = timedelta(0)


def now():
    return timezone.now() + _offset


def shift(seconds: float) -> None:
    global _offset
    _offset += timedelta(seconds=seconds)


def reset() -> None:
    global _offset
    _offset = timedelta(0)
