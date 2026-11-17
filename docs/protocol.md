# 设备通信协议（WebSocket JSON）

## 接入鉴权（接入 Key）

每台设备凭**管理员手动生成**的接入 Key 上线：

- 建档时默认不生成 Key（`POST /api/devices/` 可传 `generate_key: true` 同时生成）；在管理端「设备详情 → 接入 Key」生成，或在设备列表勾选后「批量生成 Key」（`POST /api/devices/generate-keys/`）。
- 未生成 Key / Key 已吊销的设备无法上线。重新生成或吊销后旧 Key 立即失效，已有连接被断开。
- Key 的生成、查看、吊销都记入操作审计（`KEY_GENERATE` / `KEY_VIEW` / `KEY_REVOKE`）。

### 推荐：HMAC 签名（Key 不在网络上传输）

```
ts    = 当前 Unix 时间戳（秒），与平台偏差 ≤ IOT_DEVICE_AUTH_MAX_SKEW（默认 300 秒）
nonce = 每次连接新生成的随机串，8~64 位 [A-Za-z0-9_-]，同一 nonce 在时间窗口内只能使用一次
sign  = hex( HMAC-SHA256( key = 接入Key, message = 设备编号 + "\n" + ts + "\n" + nonce ) )

ws://<host>/ws/device/<device_id>/?ts=<ts>&nonce=<nonce>&sign=<sign>
```

测试向量：设备 `dev-001`，Key `0123456789abcdef0123456789abcdef`，ts `1763380000`，nonce `a1b2c3d4e5f60718`
→ sign `f3591d4d3ba2f0926578b2d00aca065b387ce58b5206a695c83453ec463e719d`

### 兼容：明文 Key

`ws://<host>/ws/device/<device_id>/?secret=<接入Key>`。Key 会出现在 URL 与代理日志中，生产环境建议设置 `IOT_DEVICE_AUTH_ALLOW_PLAIN=0` 关闭。

### 鉴权失败

平台先完成握手，发送 `{"type": "auth_failed", "code": <关闭码>, "message": "<原因>"}`，再以同一关闭码关闭连接：

| 关闭码 | 含义 |
|---|---|
| 4400 | 缺少或格式错误的鉴权参数 |
| 4401 | 设备不存在 / Key 或签名错误 / 平台已关闭明文方式 |
| 4403 | 设备尚未生成接入 Key（或已吊销） |
| 4408 | 时间戳偏差超过允许范围（设备需 NTP 校时） |
| 4409 | nonce 重复使用 |
| 4000 | 被同一设备的新连接顶替（非鉴权错误） |

### 连接约定

- 心跳超时（周期 × N）被判离线时，平台主动断开连接，设备应重连（重新签名）并重新注册。
- 所有消息均为 JSON 对象（UTF-8，中文不转义），`type` 字段区分类型。
- 各语言完整示例：`examples/device/`（Python / C / C++ / Java），管理端「帮助 → 设备接入指南」。

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
| `auth_failed` | `code`, `message` | 鉴权失败，随后以 `code` 关闭连接。 |
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
2. 下载：`GET url?device_id=<id>&ts=<ts>&nonce=<nonce>&sign=<sign>`（签名方式同上线，也可用请求头 `X-Device-Id` / `X-Device-Ts` / `X-Device-Nonce` / `X-Device-Sign`；兼容 `secret` / `X-Device-Secret`），上报 `DOWNLOADING`。
3. 校验 SHA-256 与 `checksum` 一致，上报 `VERIFYING`；不一致上报 `FAILED`。
4. 安装，上报 `INSTALLING`（可多次带进度）。
5. 上报 `REBOOTING` 后重启，重连并 `register(version=新版本)`。
6. 平台确认版本号等于目标版本 → `SUCCESS` 并回写档案；不一致 → `FAILED`（版本确认失败）。

升级通知超时未应答时，记录重新挂起，设备上线 / 下次调度时再次下发，最多 3 次。
任一升级阶段停留超过 `IOT_UPGRADE_STAGE_TIMEOUT` 秒判定失败。
