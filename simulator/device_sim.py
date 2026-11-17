"""设备端模拟器：心跳 / 指令应答 / 升级代理。

用法：
    python simulator/device_sim.py --file data/demo_devices.json
    python simulator/device_sim.py --device dev-001:<secret>:1.0.0 --fail-rate 0.1
"""
import argparse
import asyncio
import hashlib
import hmac
import json
import random
import secrets
import time
import urllib.parse
import urllib.request

import websockets


class SimDevice:
    def __init__(self, device_id, secret, version, args):
        self.device_id, self.secret, self.version, self.args = device_id, secret, version, args
        self.ws = None
        self.rebooting = False

    def log(self, *a):
        print(f"[{self.device_id} v{self.version}]", *a, flush=True)

    def auth_params(self) -> dict:
        """HMAC-SHA256 签名鉴权：Key 不在网络上传输；--plain 时使用明文 Key。"""
        if self.args.plain:
            return {"secret": self.secret}
        ts, nonce = str(int(time.time())), secrets.token_hex(8)
        sign = hmac.new(self.secret.encode(), f"{self.device_id}\n{ts}\n{nonce}".encode(), hashlib.sha256).hexdigest()
        return {"ts": ts, "nonce": nonce, "sign": sign}

    @property
    def ws_url(self):
        base = self.args.server.replace("http://", "ws://").replace("https://", "wss://").rstrip("/")
        return f"{base}/ws/device/{self.device_id}/?{urllib.parse.urlencode(self.auth_params())}"

    async def send(self, **msg):
        await self.ws.send(json.dumps(msg, ensure_ascii=False))

    async def run(self):
        while True:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    self.ws = ws
                    await self.send(type="register", version=self.version, model="sim")
                    hb = asyncio.create_task(self.heartbeat())
                    try:
                        async for raw in ws:
                            await self.on_message(json.loads(raw))
                    finally:
                        hb.cancel()
            except (OSError, websockets.ConnectionClosed) as e:
                if not self.rebooting:
                    self.log("连接断开：", e)
            self.rebooting = False
            await asyncio.sleep(self.args.reconnect)

    async def heartbeat(self):
        while True:
            await asyncio.sleep(self.args.heartbeat)
            await self.send(type="heartbeat")

    async def on_message(self, msg):
        if msg.get("type") == "auth_failed":
            self.log(f"鉴权失败（{msg.get('code')}）：{msg.get('message')}")
            return
        if msg.get("type") == "registered":
            self.log("已上线")
            return
        if msg.get("type") != "command":
            return
        cid, code = msg["command_id"], msg["code"]
        await self.send(type="ack", command_id=cid)
        if code == "OTA_UPGRADE":
            await self.send(type="result", command_id=cid, code=0)
            asyncio.create_task(self.upgrade(msg["params"]))
            return
        await asyncio.sleep(random.uniform(0.2, 1.5))
        if random.random() < self.args.fail_rate:
            await self.send(type="result", command_id=cid, code=1, message="模拟执行失败")
            self.log("指令失败", code)
        else:
            await self.send(type="result", command_id=cid, code=0, data={"code": code, "params": msg["params"]})
            self.log("指令成功", code, msg["params"])

    async def upgrade(self, p):
        rid, pkg = p["record_id"], p["package"]
        self.log(f"开始升级 → {p['version_no']}（{pkg['type']}）")
        try:
            await self.send(type="upgrade_progress", record_id=rid, stage="DOWNLOADING", progress=0)
            q = urllib.parse.urlencode({"device_id": self.device_id, **self.auth_params()})
            data = await asyncio.to_thread(lambda: urllib.request.urlopen(f"{pkg['url']}?{q}", timeout=30).read())
            await self.send(type="upgrade_progress", record_id=rid, stage="DOWNLOADING", progress=100)
            await self.send(type="upgrade_progress", record_id=rid, stage="VERIFYING")
            if hashlib.sha256(data).hexdigest() != pkg["checksum"]:
                raise RuntimeError("升级包校验失败")
            await asyncio.sleep(0.5)
            if random.random() < self.args.upgrade_fail_rate:
                raise RuntimeError("模拟安装失败")
            for pct in (20, 60, 100):
                await self.send(type="upgrade_progress", record_id=rid, stage="INSTALLING", progress=pct)
                await asyncio.sleep(0.4)
            await self.send(type="upgrade_progress", record_id=rid, stage="REBOOTING")
            self.version = p["version_no"]
            self.rebooting = True
            await self.ws.close()  # 模拟重启：断开后以新版本重新注册
            self.log("重启中")
        except Exception as e:  # noqa: BLE001
            await self.send(type="upgrade_progress", record_id=rid, stage="FAILED", error=str(e))
            self.log("升级失败：", e)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:8000")
    ap.add_argument("--file", help="init_demo 导出的设备列表 JSON")
    ap.add_argument("--device", action="append", default=[], help="id:secret[:version]")
    ap.add_argument("--heartbeat", type=float, default=10)
    ap.add_argument("--plain", action="store_true", help="使用明文 Key（secret=）而非 HMAC 签名")
    ap.add_argument("--reconnect", type=float, default=2)
    ap.add_argument("--fail-rate", type=float, default=0.0)
    ap.add_argument("--upgrade-fail-rate", type=float, default=0.0)
    args = ap.parse_args()

    items = []
    if args.file:
        items += json.load(open(args.file, encoding="utf-8"))
    for spec in args.device:
        parts = spec.split(":")
        items.append({"device_id": parts[0], "secret": parts[1], "version": parts[2] if len(parts) > 2 else "1.0.0"})
    if not items:
        ap.error("需要 --file 或 --device")
    await asyncio.gather(*(SimDevice(i["device_id"], i["secret"], i.get("version") or "1.0.0", args).run()
                           for i in items))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
