# 物联网设备管理平台设计

> 原始设计文档，平台实现以此为准。

## 一、功能架构

```
┌──────────────────────────────────────────────────────────┐
│                     管理端（统一操作界面）                     │
├──────────────────┬──────────────────┬────────────────────┤
│  设备在线管理      │   设备控制          │  系统版本管理          │
│ · 设备信息展示     │ · 指令下发          │ · 版本信息维护          │
│ · 实时在线/离线    │ · 执行结果反馈      │ · 升级包管理            │
│ · 状态变更记录     │ · 批量控制          │ · 版本发布 / 回滚        │
│ · 筛选查询        │ · 关键操作记录      │ · 升级状态跟踪          │
├──────────────────┴──────────────────┴────────────────────┤
│ 公共支撑：设备档案 │ 设备通信通道（上行/下行） │ 任务调度 │ 操作审计 │
├──────────────────────────────────────────────────────────┤
│                       设备端（心跳 / 应答 / 升级代理）           │
└──────────────────────────────────────────────────────────┘
```

### 1. 设备在线管理

- 设备信息展示：编号、名称、型号、分组、当前版本、最近上线时间、在线状态。
- 实时状态：基于心跳与连接事件判定在线/离线，状态变化实时推送到管理端。
- 状态变更记录：每次上线、离线、超时都留痕，含原因与持续时长。
- 筛选查询：按状态、型号、分组、版本、时间区间组合筛选，支持分页与导出。

### 2. 设备控制

- 指令下发：按指令模板选择命令、填写参数，下发到单台设备。
- 结果反馈：跟踪 待发送 → 已送达 → 执行成功/失败/超时，回显设备返回数据。
- 批量控制：按设备列表、分组或筛选条件生成批次，分批并发下发，汇总成功率。
- 关键操作记录：重启、恢复出厂、参数修改等高风险指令需二次确认并全量留痕。

### 3. 设备系统版本管理

- 版本信息维护：版本号、适用型号、最低可升级版本、更新说明、状态（草稿/可发布/已废弃）。
- 升级包管理：上传、校验值（完整性）、签名、大小、全量/差分包标识。
- 发布/回滚：选择目标设备范围，支持灰度（按比例或指定设备）→ 全量；异常时回滚到指定旧版本。
- 升级状态跟踪：逐台记录 下载 → 校验 → 安装 → 重启 → 版本确认，任务级汇总进度和失败原因。

## 二、模块关系

```
            设备档案（唯一数据源）
           ↙        ↓          ↘
   在线管理 ──状态──→ 设备控制    版本管理
       │   （离线不下发/排队）       │
       │                        │ 升级指令复用控制通道
       └──────在线状态────────────→│ （离线设备挂起，上线后续升）
                                 │
   设备上报版本号 ──────────────────→ 更新档案中的当前版本

   设备控制、版本发布/回滚 ────────→ 操作审计（统一记录）
```

- 在线管理是前置条件：控制与升级下发前先查在线状态；离线设备的指令按策略丢弃或排队，升级任务挂起待上线。
- 版本管理依赖控制通道：升级通知本质是一条特殊控制指令，复用下发与回执机制。
- 状态回写档案：心跳更新在线状态，升级完成后设备上报新版本号回写档案。
- 统一审计：关键控制和版本发布/回滚都写入同一操作记录，便于追溯。

## 三、核心数据结构

**设备 Device**

| 字段 | 说明 |
|---|---|
| device_id | 设备唯一标识 |
| name / model / group_id | 名称、型号、分组 |
| current_version | 当前系统版本 |
| online_status | ONLINE / OFFLINE |
| last_heartbeat_at | 最近心跳时间 |
| last_online_at / last_offline_at | 最近上线/离线时间 |
| created_at / updated_at | 创建/更新时间 |

**状态变更记录 DeviceStatusLog**

| 字段 | 说明 |
|---|---|
| log_id / device_id | 记录编号、设备 |
| from_status / to_status | 变更前后状态 |
| reason | 主动上线、主动断开、心跳超时等 |
| occurred_at | 发生时间 |

**指令模板 CommandTemplate**

| 字段 | 说明 |
|---|---|
| template_id / code / name | 指令编码与名称 |
| applicable_models | 适用型号 |
| param_schema | 参数定义 |
| is_critical | 是否关键操作（需确认与审计） |
| timeout_seconds | 执行超时时间 |

**控制指令 Command**

| 字段 | 说明 |
|---|---|
| command_id / batch_id | 指令编号、所属批次（单发为空） |
| device_id / template_id | 目标设备、指令模板 |
| params | 下发参数 |
| status | PENDING / SENT / DELIVERED / SUCCESS / FAILED / TIMEOUT |
| result_code / result_data | 设备返回结果 |
| operator_id | 操作人 |
| sent_at / finished_at | 下发/完成时间 |

**批量任务 CommandBatch**

| 字段 | 说明 |
|---|---|
| batch_id / template_id / params | 批次、指令及参数 |
| target_scope | 设备列表或筛选条件快照 |
| total / success / failed / pending | 统计数 |
| status | RUNNING / COMPLETED / PARTIAL_FAILED / CANCELLED |

**系统版本 FirmwareVersion**

| 字段 | 说明 |
|---|---|
| version_id / version_no | 版本标识、版本号 |
| applicable_models | 适用型号 |
| min_upgradable_version | 最低可升级起点 |
| release_notes | 更新说明 |
| status | DRAFT / RELEASABLE / DEPRECATED |

**升级包 UpgradePackage**

| 字段 | 说明 |
|---|---|
| package_id / version_id | 包编号、所属版本 |
| package_type | FULL / DIFF |
| base_version | 差分包的起始版本 |
| file_ref / size / checksum / signature | 文件引用、大小、校验值、签名 |

**升级任务 UpgradeTask**

| 字段 | 说明 |
|---|---|
| task_id / version_id | 任务、目标版本 |
| task_type | UPGRADE / ROLLBACK |
| target_scope / gray_ratio | 目标范围、灰度比例 |
| failure_threshold | 失败率阈值（超过自动暂停） |
| status | CREATED / GRAY / FULL / PAUSED / COMPLETED / ROLLED_BACK |
| operator_id / created_at | 操作人、创建时间 |

**设备升级记录 DeviceUpgradeRecord**

| 字段 | 说明 |
|---|---|
| record_id / task_id / device_id | 记录、任务、设备 |
| from_version / to_version | 升级前后版本 |
| stage | WAITING / DOWNLOADING / VERIFYING / INSTALLING / REBOOTING / SUCCESS / FAILED |
| progress / error_msg | 进度、失败原因 |
| updated_at | 更新时间 |

**操作记录 OperationLog**

| 字段 | 说明 |
|---|---|
| op_id / operator_id | 记录、操作人 |
| op_type | 关键指令、批量控制、版本发布、回滚等 |
| target | 设备/批次/任务 |
| detail / result | 操作内容、结果 |
| op_time | 操作时间 |

## 四、主要业务流程

### 1. 在线状态判定

- 设备连接后上报注册/心跳，平台更新 last_heartbeat_at，状态由 OFFLINE → ONLINE，写 DeviceStatusLog。
- 设备周期心跳；平台定时扫描，超过 心跳周期 × N 未收到则判定离线（原因：心跳超时）。
- 设备主动断开立即置离线（原因：主动断开）。
- 状态变化实时推送管理端，并通知控制与升级模块（如触发挂起任务）。

### 2. 单设备控制

- 操作人选择设备与指令模板，填参数；关键指令需二次确认。
- 校验：设备存在、型号匹配、参数合法、设备在线。
- 生成 Command（PENDING）→ 下发（SENT）→ 设备确认（DELIVERED）。
- 设备执行后回执 → SUCCESS/FAILED；超时未回执 → TIMEOUT。
- 结果回显管理端；关键指令写 OperationLog。

### 3. 批量控制

- 按设备列表、分组或筛选条件确定范围，保存范围快照，生成 CommandBatch。
- 拆分为逐台 Command，按并发上限分批下发；离线设备按策略标记失败或排队。
- 实时汇总成功/失败/待执行数；可中途取消未下发部分。
- 结束后状态为 COMPLETED 或 PARTIAL_FAILED，支持对失败设备一键重试；全程写 OperationLog。

### 4. 版本发布与升级

- 维护版本信息 → 上传升级包 → 校验完整性与签名 → 版本置为 RELEASABLE。
- 创建 UpgradeTask：选择目标版本与范围，自动排除型号不符、低于最低可升级版本或已是目标版本的设备。
- 灰度阶段：按比例或指定设备下发升级通知；在线设备立即执行，离线设备挂起待上线。
- 设备按阶段上报：下载 → 校验 → 安装 → 重启 → 上报新版本号，平台更新 DeviceUpgradeRecord 并回写设备 current_version。
- 灰度失败率未超阈值 → 操作人确认后推进全量；超过阈值 → 任务自动 PAUSED。
- 全部设备终态后任务 COMPLETED；发布动作写 OperationLog。

### 5. 版本回滚

- 触发条件：灰度/全量失败率过高，或升级后发现问题。
- 暂停原任务，选择回滚目标版本（须为该型号可用旧版本）。
- 生成 ROLLBACK 类型 UpgradeTask，范围为已升级成功的设备，流程同升级。
- 原任务标记 ROLLED_BACK，回滚过程写 OperationLog。

## 五、关键状态机

- 设备在线：OFFLINE ⇄ ONLINE（心跳/连接 → 上线；超时/断开 → 离线）

- 控制指令：PENDING → SENT → DELIVERED → SUCCESS | FAILED，任一非终态超时 → TIMEOUT

- 设备升级：WAITING → DOWNLOADING → VERIFYING → INSTALLING → REBOOTING → SUCCESS，任一阶段出错 → FAILED（可重试或回滚）

- 升级任务：CREATED → GRAY → FULL → COMPLETED，GRAY/FULL → PAUSED → 继续 | ROLLED_BACK

