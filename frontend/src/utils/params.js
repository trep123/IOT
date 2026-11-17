/** 只提交填写了的字段；必填缺失返回错误说明 */
export function collectParams(schema, model) {
  const out = {}
  for (const [k, s] of Object.entries(schema || {})) {
    const v = model[k]
    if (v === undefined || v === null || v === '') {
      if (s.required) throw new Error(`参数 ${k} 必填`)
      continue
    }
    out[k] = v
  }
  return out
}

/** 目标范围校验：返回错误说明，合法时返回空字符串 */
export function scopeError(s) {
  if (!s) return '请选择目标范围'
  if (s.device_ids && !s.device_ids.length) return '请至少选择一台设备'
  if ('group_id' in s && !s.group_id) return '请选择分组'
  if (s.filters && !Object.keys(s.filters).length) return '请至少选择一个筛选条件，或切换到「全部设备」'
  return ''
}
