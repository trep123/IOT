// 枚举值 → 中文与标签颜色，和后端 TextChoices 保持一致
const mk = (pairs) => Object.fromEntries(pairs.map(([k, label, type]) => [k, { label, type }]))

export const ONLINE = mk([['ONLINE', '在线', 'success'], ['OFFLINE', '离线', 'info']])
export const STATUS_REASON = mk([
  ['REGISTER', '主动上线', 'success'], ['HEARTBEAT_RESUME', '心跳恢复', 'success'],
  ['DISCONNECT', '主动断开', 'warning'], ['HEARTBEAT_TIMEOUT', '心跳超时', 'danger'],
])
export const COMMAND = mk([
  ['PENDING', '待发送', 'info'], ['SENT', '已发送', 'primary'], ['DELIVERED', '已送达', 'primary'],
  ['SUCCESS', '执行成功', 'success'], ['FAILED', '执行失败', 'danger'], ['TIMEOUT', '超时', 'warning'],
  ['CANCELLED', '已取消', 'info'],
])
export const BATCH = mk([
  ['RUNNING', '执行中', 'primary'], ['COMPLETED', '已完成', 'success'],
  ['PARTIAL_FAILED', '部分失败', 'warning'], ['CANCELLED', '已取消', 'info'],
])
export const OFFLINE_POLICY = mk([['REJECT', '离线即失败', ''], ['QUEUE', '排队待上线', '']])
export const VERSION = mk([['DRAFT', '草稿', 'info'], ['RELEASABLE', '可发布', 'success'], ['DEPRECATED', '已废弃', 'danger']])
export const PACKAGE_TYPE = mk([['FULL', '全量包', ''], ['DIFF', '差分包', 'warning']])
export const TASK = mk([
  ['CREATED', '已创建', 'info'], ['GRAY', '灰度中', 'warning'], ['FULL', '全量中', 'primary'],
  ['PAUSED', '已暂停', 'danger'], ['COMPLETED', '已完成', 'success'], ['ROLLED_BACK', '已回滚', 'info'],
])
export const TASK_TYPE = mk([['UPGRADE', '升级', 'primary'], ['ROLLBACK', '回滚', 'warning']])
export const STAGE = mk([
  ['WAITING', '等待', 'info'], ['DOWNLOADING', '下载中', 'primary'], ['VERIFYING', '校验中', 'primary'],
  ['INSTALLING', '安装中', 'primary'], ['REBOOTING', '重启中', 'warning'], ['SUCCESS', '成功', 'success'],
  ['FAILED', '失败', 'danger'],
])
export const STAGE_ORDER = ['WAITING', 'DOWNLOADING', 'VERIFYING', 'INSTALLING', 'REBOOTING', 'SUCCESS']
export const PHASE = mk([['GRAY', '灰度', 'warning'], ['FULL', '全量', 'primary']])
export const OP_TYPE = mk([
  ['CRITICAL_COMMAND', '关键指令下发', 'danger'], ['CRITICAL_COMMAND_RESULT', '关键指令结果', 'danger'],
  ['BATCH_CONTROL', '批量控制', 'primary'], ['BATCH_CANCEL', '取消批次', 'info'],
  ['VERSION_CREATE', '创建版本', ''], ['VERSION_PUBLISH', '版本发布', 'success'], ['VERSION_DEPRECATE', '版本废弃', 'info'],
  ['PACKAGE_UPLOAD', '上传升级包', ''], ['UPGRADE_CREATE', '创建升级任务', ''], ['UPGRADE_START', '开始灰度', 'warning'],
  ['UPGRADE_PROMOTE', '推进全量', 'primary'], ['UPGRADE_PAUSE', '暂停升级', 'warning'],
  ['UPGRADE_AUTO_PAUSE', '失败率超阈值自动暂停', 'danger'], ['UPGRADE_RESUME', '继续升级', 'success'],
  ['UPGRADE_RETRY', '重试失败设备', ''], ['ROLLBACK', '版本回滚', 'danger'],
  ['KEY_GENERATE', '生成接入Key', 'warning'], ['KEY_REVOKE', '吊销接入Key', 'danger'], ['KEY_VIEW', '查看接入Key', 'info'],
])
export const TARGET_TYPE = mk([
  ['DEVICE', '设备', ''], ['COMMAND', '指令', ''], ['BATCH', '批次', ''], ['VERSION', '版本', ''],
  ['PACKAGE', '升级包', ''], ['TASK', '升级任务', ''],
])

export const options = (dict) => Object.entries(dict).map(([value, v]) => ({ value, label: v.label }))
