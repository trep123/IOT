"""端到端：真实 WebSocket 连接 + Channel Layer 下行。"""
import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator

from control.models import Command, CommandTemplate
from devices.models import Device
from iot_platform.asgi import application

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.asyncio
async def test_device_websocket_flow(user):
    d = await sync_to_async(Device.objects.create)(device_id="ws-1", name="ws", model="GW-100",
                                                    current_version="1.0.0")
    tpl = await sync_to_async(CommandTemplate.objects.create)(code="PING", name="ping", applicable_models=["*"])

    bad = WebsocketCommunicator(application, "/ws/device/ws-1/?secret=wrong")
    connected, code = await bad.connect()
    assert not connected

    ws = WebsocketCommunicator(application, f"/ws/device/ws-1/?secret={d.secret}")
    connected, _ = await ws.connect()
    assert connected
    await ws.send_json_to({"type": "register", "version": "1.0.0"})
    reply = await ws.receive_json_from(timeout=3)
    assert reply["type"] == "registered"
    assert (await sync_to_async(Device.objects.get)(pk="ws-1")).online_status == "ONLINE"

    from control import services
    from django.db import transaction

    def send_cmd():
        with transaction.atomic():
            dev = Device.objects.get(pk="ws-1")
            return services.create_command(dev, tpl, {}, "tester").command_id
    cid = await sync_to_async(send_cmd)()
    msg = await ws.receive_json_from(timeout=3)
    assert msg["type"] == "command" and msg["command_id"] == cid
    await ws.send_json_to({"type": "result", "command_id": cid, "code": 0, "data": {"pong": True}})
    await ws.send_json_to({"type": "heartbeat"})  # 等待上一条消息处理完
    await ws.disconnect()
    cmd = await sync_to_async(Command.objects.get)(pk=cid)
    assert cmd.status == "SUCCESS"
    assert (await sync_to_async(Device.objects.get)(pk="ws-1")).online_status == "OFFLINE"
