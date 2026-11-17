import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

export const fmtTime = (v) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '—')
export const fromNow = (v) => (v ? dayjs(v).fromNow() : '—')
export const pct = (v, digits = 1) => (v === null || v === undefined ? '—' : `${(v * 100).toFixed(digits)}%`)

export function fmtDuration(sec) {
  if (sec === null || sec === undefined) return '—'
  const s = Math.max(0, Math.round(sec))
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60)
  if (d) return `${d}天${h}小时`
  if (h) return `${h}小时${m}分`
  if (m) return `${m}分${s % 60}秒`
  return `${s}秒`
}

export function fmtSize(n) {
  if (!n && n !== 0) return '—'
  const u = ['B', 'KB', 'MB', 'GB']
  let i = 0
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++ }
  return `${n.toFixed(i ? 1 : 0)} ${u[i]}`
}

/** 目标范围的可读描述 */
export function scopeText(scope = {}, groupName) {
  if (!scope) return '—'
  // 后端保存的快照：{ scope: 原始条件, device_ids: 解析出的设备 }
  if (scope.scope) return scopeText(scope.scope, groupName)
  if (scope.rollback_of) return `任务 #${scope.rollback_of} 中已升级的设备`
  if (scope.all) return '全部设备'
  if (scope.device_ids) return `指定 ${scope.device_ids.length} 台设备`
  if (scope.group_id) return `分组：${groupName?.(scope.group_id) ?? scope.group_id}`
  if (scope.filters) {
    const f = scope.filters
    const parts = []
    if (f.model) parts.push(`型号 ${f.model}`)
    if (f.model__in) parts.push(`型号 ${f.model__in}`)
    if (f.version) parts.push(`版本 ${f.version}`)
    if (f.online_status) parts.push(f.online_status === 'ONLINE' ? '仅在线' : '仅离线')
    if (f.group_id) parts.push(`分组 ${groupName?.(f.group_id) ?? f.group_id}`)
    return `条件：${parts.join('，') || '全部'}`
  }
  return JSON.stringify(scope)
}
