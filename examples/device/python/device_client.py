"""IoT 设备接入示例（Python 3.8+）。

依赖：pip install websockets
运行：python device_client.py http://<平台地址>:8090 <设备编号> <接入Key> [当前版本]

流程：HMAC 签名建连 → register 上报版本 → 按平台下发的周期发心跳
     → 收到 command 先回 ack，执行后回 result → 断线指数退避重连
"""
import asyncio
import hashlib
import hmac
import json
import secrets
import sys
import time
import urllib.parse

import websockets

SERVER, DEVICE_ID, DEVICE_KEY = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3]
VERSION = sys.argv[4] if len(sys.argv) > 4 else "1.0.0"


def build_url() -> str:
    """签名串 = 设备编号 \\n 时间戳 \\n 随机串，HMAC-SHA256(Key) 后转十六进制。Key 本身不上传。"""
    ts, nonce = str(int(time.time())), secrets.token_hex(8)
    payload = f"{DEVICE_ID}\n{ts}\n{nonce}".encode()
    sign = hmac.new(DEVICE_KEY.encode(), payload, hashlib.sha256).hexdigest()
    base = SERVER.replace("https://", "wss://").replace("http://", "ws://")
    query = urllib.parse.urlencode({"ts": ts, "nonce": nonce, "sign": sign})
    return f"{base}/ws/device/{urllib.parse.quote(DEVICE_ID)}/?{query}"


def execute(code: str, params: dict):
    """执行业务指令，返回 (code, data, message)。code=0 表示成功。在这里对接真实硬件。"""
    if code == "PING":
        return 0, {"pong": True}, ""
    if code in ("REBOOT", "SET_PARAM", "SET_LED", "FACTORY_RESET"):
        print(f"执行 {code} 参数 {params}")
        return 0, {"code": code}, ""
    if code == "OTA_UPGRADE":
        # 升级流程（下载、校验、安装、上报进度）见 docs/protocol.md 与 simulator/device_sim.py
        return 1, None, "示例未实现升级"
    return 1, None, f"不支持的指令 {code}"


async def session(ws):
    send = lambda **m: ws.send(json.dumps(m, ensure_ascii=False))  # noqa: E731
    await send(type="register", version=VERSION)
    heartbeat_task = None

    async def heartbeat(interval):
        while True:
            await asyncio.sleep(interval)
            await send(type="heartbeat")

    try:
        async for raw in ws:
            msg = json.loads(raw)
            mtype = msg.get("type")
            if mtype == "registered":
                interval = msg.get("heartbeat_interval", 30)
                print(f"上线成功，心跳周期 {interval}s")
                heartbeat_task = asyncio.create_task(heartbeat(interval))
            elif mtype == "command":
                cid = msg["command_id"]
                await send(type="ack", command_id=cid)
                code, data, message = execute(msg["code"], msg.get("params") or {})
                await send(type="result", command_id=cid, code=code, data=data, message=message)
            elif mtype == "auth_failed":
                print(f"鉴权失败 {msg['code']}：{msg['message']}")
            elif mtype == "error":
                print("平台提示：", msg.get("message"))
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()


async def main():
    backoff = 1
    while True:
        code = None
        try:
            async with websockets.connect(build_url(), ping_interval=None) as ws:
                try:
                    await session(ws)
                except websockets.ConnectionClosed:
                    pass
                code = ws.close_code
        except (OSError, websockets.WebSocketException) as e:
            print("连接失败：", e)
        # 4401 Key 错误 / 4403 未生成 Key：等待更久再试，避免刷屏；4000 被新连接顶替
        backoff = 60 if code in (4401, 4403) else (1 if code == 4000 else min(backoff * 2, 60))
        print(f"连接关闭（{code}），{backoff}s 后重连")
        await asyncio.sleep(backoff)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    asyncio.run(main())
