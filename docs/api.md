# REST API（Django REST Framework）

- 前缀：`/api/`；可浏览 API：浏览器登录 `/api/auth/login/` 后直接访问。
- 认证：`Authorization: Token <token>`（`POST /api/auth/token/` 用 `username`、`password` 换取），或 Session。
- 列表统一分页格式：`{"count", "next", "previous", "results"}`，参数 `page`、`page_size`（≤500）。
- 通用参数：`search`（模糊搜索）、`ordering`（排序，`-` 前缀倒序）、各资源的筛选字段。
- 错误格式：DRF 标准，字段校验错误 `400 {"字段": ["原因"]}`，其他 `{"detail": "原因"}`；状态冲突返回 `409`。

## 设备在线管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/groups/` | 分组列表 / 新建 |
| GET/PUT/PATCH/DELETE | `/api/groups/{id}/` | 分组详情 |
| GET/POST | `/api/devices/` | 设备列表 / 建档（响应含一次性 `secret`） |
| GET/PUT/PATCH/DELETE | `/api/devices/{device_id}/` | 设备档案；`online_status` 等由心跳维护，只读 |
| GET | `/api/devices/{device_id}/status-logs/` | 该设备的状态变更记录 |
| GET | `/api/devices/{device_id}/secret/` | 查看接入密钥 |
| POST | `/api/devices/{device_id}/reset-secret/` | 重置接入密钥 |
| GET | `/api/devices/summary/` | 在线/离线、型号、版本统计（支持同样的筛选参数） |
| GET | `/api/devices/export/` | 按筛选条件导出 CSV |
| GET | `/api/status-logs/` | 全部状态变更记录；`/api/status-logs/export/` 导出 |

设备筛选参数：`online_status`、`model`、`model__in`、`group_id`、`version`、`device_id__in`、
`last_online_after`/`last_online_before`、`created_after`/`created_before`（ISO 8601）、`search`、`ordering`。

## 设备控制

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/command-templates/` | 指令模板（`param_schema`、`is_critical`、`timeout_seconds`、`applicable_models`） |
| GET/PUT/PATCH/DELETE | `/api/command-templates/{id}/` | 系统内置模板（`OTA_UPGRADE`）不可改删 |
| POST | `/api/commands/` | 单设备下发：`device_id`、`template_id`、`params`、`confirm`（关键操作必须 `true`）、`offline_policy`（`REJECT` 离线返回 409 / `QUEUE` 排队） |
| GET | `/api/commands/`、`/api/commands/{id}/` | 指令结果；筛选 `device_id`、`batch_id`、`status`、`status__in`、`template_code`、`is_critical`、时间区间 |
| POST | `/api/command-batches/` | 批量控制：`template_id`、`params`、`target_scope`、`offline_policy`（`REJECT` 标记失败 / `QUEUE` 排队）、`concurrency`、`confirm` |
| GET | `/api/command-batches/`、`/{id}/` | 批次统计：`total`/`success`/`failed`/`pending`/`cancelled`/`success_rate` |
| GET | `/api/command-batches/{id}/commands/` | 批次明细（支持指令筛选参数） |
| POST | `/api/command-batches/{id}/cancel/` | 取消未下发部分 |
| POST | `/api/command-batches/{id}/retry/` | 失败/超时设备一键重试（生成新批次，`retry_of` 指向原批次；关键指令需 `confirm`） |

`target_scope` 四选一：`{"device_ids": [...]}`、`{"group_id": 1}`、`{"filters": {"model": "GW-100", "online_status": "ONLINE"}}`（与设备列表筛选参数一致）、`{"all": true}`。批次会保存范围快照（原始条件 + 解析出的设备列表）。

`param_schema` 示例：`{"level": {"type": "int", "required": true, "min": 0, "max": 100}, "mode": {"type": "str", "enum": ["a", "b"], "default": "a"}}`，`type` 取 `int`/`float`/`str`/`bool`。

## 系统版本管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/firmware-versions/` | 版本信息（新建为 `DRAFT`）；筛选 `status`、`version_no`、`model` |
| GET/PUT/PATCH/DELETE | `/api/firmware-versions/{id}/` | `status` 只读；仅草稿可删除 |
| POST | `/api/firmware-versions/{id}/publish/` | DRAFT → RELEASABLE（需至少一个校验通过的全量包） |
| POST | `/api/firmware-versions/{id}/deprecate/` | → DEPRECATED（无未结束任务时） |
| POST | `/api/upgrade-packages/` | multipart 上传：`version_id`、`package_type`(FULL/DIFF)、`base_version`(差分必填)、`file`、可选 `checksum`（不一致则拒绝） |
| GET/DELETE | `/api/upgrade-packages/`、`/{id}/` | 平台自动计算 SHA-256、大小，并以 HMAC-SHA256 签名 |
| POST | `/api/upgrade-packages/{id}/verify/` | 重新校验文件完整性与签名 |
| GET | `/api/upgrade-packages/{id}/download/` | 下载（管理端 Token 或设备 `device_id`+`secret`） |
| POST | `/api/upgrade-tasks/` | 创建任务：`version_id`、`target_scope`、`gray_ratio`、`gray_device_ids`、`failure_threshold`、`start` |
| GET | `/api/upgrade-tasks/`、`/{id}/` | 含 `stats`（总数、成功、失败、阶段分布、灰度统计、失败率）与 `excluded`（自动排除的设备及原因） |
| GET | `/api/upgrade-tasks/{id}/records/` | 逐台升级记录 |
| POST | `/api/upgrade-tasks/{id}/start/` | CREATED → GRAY（灰度比例为 1 时直接 FULL） |
| POST | `/api/upgrade-tasks/{id}/promote/` | GRAY → FULL（灰度失败率需未超阈值） |
| POST | `/api/upgrade-tasks/{id}/pause/` | 暂停（`reason`） |
| POST | `/api/upgrade-tasks/{id}/resume/` | 继续（已发生的失败视为已确认，不再计入熔断） |
| POST | `/api/upgrade-tasks/{id}/retry-failed/` | 失败设备重试 |
| POST | `/api/upgrade-tasks/{id}/rollback/` | 回滚：`target_version_id`（必须是更旧的可发布版本）、`gray_ratio`、`failure_threshold`；返回原任务与回滚任务 |
| GET | `/api/upgrade-records/` | 全部升级记录；筛选 `task_id`、`device_id`、`stage`、`phase` |

创建任务时自动排除：型号不适用、已是目标版本、低于最低可升级版本、高于目标版本（应走回滚）、已在其他未完成任务中、无可用升级包。差分包按 `base_version == 设备当前版本` 优先匹配，否则用全量包。

## 操作审计

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/operation-logs/`、`/{id}/` | 筛选 `operator_id`、`op_type`、`target_type`、`target_id`、`result`、`op_time_after`/`op_time_before` |
| GET | `/api/operation-logs/export/` | 导出 CSV |

记录类型：关键指令下发 / 结果、批量控制、取消批次、上传升级包、版本发布 / 废弃、创建升级任务、开始灰度、推进全量、暂停、自动暂停、继续、重试、版本回滚。

## 实时推送

`ws://<host>/ws/admin/?token=<token>`，消息格式 `{"event": "...", "data": {...}}`：

| event | 触发 |
|---|---|
| `device_status` | 上线 / 离线（含原因） |
| `device_version` | 设备版本号变化 |
| `command_update` | 指令状态变化 |
| `batch_update` | 批次统计变化 |
| `task_update` | 升级任务状态 / 统计变化（含自动暂停原因） |
| `upgrade_record` | 单台升级阶段 / 进度变化 |
