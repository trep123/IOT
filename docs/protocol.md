# 设备通信协议（WebSocket JSON）

连接地址：`ws://<host>/ws/device/<device_id>/?secret=<设备密钥>`

- 设备密钥在设备建档时生成（`POST /api/devices/` 的响应中返回一次，之后可通过 `GET /api/devices/{id}/secret/` 或 `POST /api/devices/{id}/reset-secret/` 获取 / 重置）。
- 鉴权失败：连接以 `4401` 关闭。同一设备重复连接时旧连接以 `4000` 关闭（新连接顶替）。
- 心跳超时（周期 × N）被判离线时，平台主动断开连接，设备应重连并重新注册。
- 所有消息均为 JSON 对象，`type` 字段区分类型。

## 上行（设备 → 平台）

| type | 字段 | 说明 |
|---|---|---|
| `register` | `version` | 连接后第一条消息。上报当前版本号（回写档案、用于升级版本确认），置为在线。 |
| `heartbeat` | — | 周期心跳，间隔见 `registered.heartbeat_interval`。任何业务消息也会刷新心跳时间。 |
| `ack` | `command_id` | 指令已送达：SENT → DELIVERED。 |
| `result` | `command_id`, `code`, `data`, `message` | 执行结果。`code=0` 为成功，其余为失败，`message` 为失败原因。 |
| `upgrade_progress` | `record_id`, `stage`, `progress`, `error` | 升级阶段上报：`DOWNLOADING` / `VERIFYING` / `INSTALLING` / `REBOOTING` / `FAILED`。阶段只能前进，同阶段可更新 `progress`(0-100)。 |
| `version_report` | `version` | 单独上报版本号（重启后也可直接用 `register` 携带）。 |

## 下行（平台 → 设备）

| type | 字段 | 说明 |
|---|---|---|
| `registered` | `server_time`, `heartbeat_interval` | 注册成功应答。 |
| `command` | `command_id`, `code`, `params`, `timeout` | 控制指令。设备收到后先回 `ack`，执行后回 `result`。 |
| `error` | `message` | 消息格式错误等。 |

### 升级通知（复用控制指令）

升级通知就是一条 `code = "OTA_UPGRADE"` 的 `command`，`params` 结构：

```json
{
  "record_id": 12, "task_id": 3, "task_type": "UPGRADE", "version_no": "1.1.0",
  "package": {
    "package_id": 5, "type": "DIFF", "base_version": "1.0.0", "size": 20480,
    "checksum": "<sha256>", "signature": "<hmac-sha256(checksum)>",
    "url": "http://<host>/api/upgrade-packages/5/download/"
  }
}
```

设备端流程：

1. `ack` + `result(code=0)` 表示接受升级（`code≠0` 表示拒绝，记录直接失败）。
2. 下载：`GET url?device_id=<id>&secret=<密钥>`（或使用 `X-Device-Id` / `X-Device-Secret` 请求头），上报 `DOWNLOADING`。
3. 校验 SHA-256 与 `checksum` 一致，上报 `VERIFYING`；不一致上报 `FAILED`。
4. 安装，上报 `INSTALLING`（可多次带进度）。
5. 上报 `REBOOTING` 后重启，重连并 `register(version=新版本)`。
6. 平台确认版本号等于目标版本 → `SUCCESS` 并回写档案；不一致 → `FAILED`（版本确认失败）。

升级通知超时未应答时，记录重新挂起，设备上线 / 下次调度时再次下发，最多 3 次。
任一升级阶段停留超过 `IOT_UPGRADE_STAGE_TIMEOUT` 秒判定失败。
