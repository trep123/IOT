import http, { download } from './http'

/** 去掉空值，避免把空字符串作为筛选条件发给 DRF */
export function clean(params = {}) {
  const out = {}
  for (const [k, v] of Object.entries(params)) {
    if (v === '' || v === null || v === undefined) continue
    if (Array.isArray(v)) { if (v.length) out[k] = v.join(','); continue }
    out[k] = v
  }
  return out
}

const g = (url, params, cfg) => http.get(url, { params: clean(params), ...cfg }).then((r) => r.data)
const p = (url, data, cfg) => http.post(url, data, cfg).then((r) => r.data)
const pa = (url, data) => http.patch(url, data).then((r) => r.data)
const d = (url) => http.delete(url).then((r) => r.data)

/** 拉取全部分页（下拉选项等小数据量场景） */
export async function all(url, params = {}) {
  return (await g(url, { ...params, page_size: 500 })).results
}

export const auth = {
  login: (username, password) => p('auth/token/', { username, password }, { silent: true }),
}

export const groups = {
  list: (q) => g('groups/', q),
  all: () => all('groups/'),
  create: (data) => p('groups/', data),
  update: (id, data) => pa(`groups/${id}/`, data),
  remove: (id) => d(`groups/${id}/`),
}

export const devices = {
  list: (q) => g('devices/', q),
  get: (id) => g(`devices/${encodeURIComponent(id)}/`),
  create: (data) => p('devices/', data),
  update: (id, data) => pa(`devices/${encodeURIComponent(id)}/`, data),
  remove: (id) => d(`devices/${encodeURIComponent(id)}/`),
  summary: (q) => g('devices/summary/', q),
  secret: (id) => g(`devices/${encodeURIComponent(id)}/secret/`),
  resetSecret: (id) => p(`devices/${encodeURIComponent(id)}/reset-secret/`),
  statusLogs: (id, q) => g(`devices/${encodeURIComponent(id)}/status-logs/`, q),
  export: (q) => download('devices/export/', clean(q), 'devices.csv'),
}

export const statusLogs = {
  list: (q) => g('status-logs/', q),
  export: (q) => download('status-logs/export/', clean(q), 'status-logs.csv'),
}

export const templates = {
  list: (q) => g('command-templates/', q),
  all: () => all('command-templates/'),
  create: (data) => p('command-templates/', data),
  update: (id, data) => pa(`command-templates/${id}/`, data),
  remove: (id) => d(`command-templates/${id}/`),
}

export const commands = {
  list: (q) => g('commands/', q),
  get: (id) => g(`commands/${id}/`),
  create: (data) => p('commands/', data),
}

export const batches = {
  list: (q) => g('command-batches/', q),
  get: (id) => g(`command-batches/${id}/`),
  create: (data) => p('command-batches/', data),
  commands: (id, q) => g(`command-batches/${id}/commands/`, q),
  cancel: (id) => p(`command-batches/${id}/cancel/`),
  retry: (id, confirm = false) => p(`command-batches/${id}/retry/`, { confirm }),
}

export const versions = {
  list: (q) => g('firmware-versions/', q),
  all: (q) => all('firmware-versions/', q),
  get: (id) => g(`firmware-versions/${id}/`),
  create: (data) => p('firmware-versions/', data),
  update: (id, data) => pa(`firmware-versions/${id}/`, data),
  remove: (id) => d(`firmware-versions/${id}/`),
  publish: (id) => p(`firmware-versions/${id}/publish/`),
  deprecate: (id) => p(`firmware-versions/${id}/deprecate/`),
}

export const packages = {
  list: (q) => g('upgrade-packages/', q),
  upload: (form, onProgress) => p('upgrade-packages/', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => onProgress && e.total && onProgress(Math.round((e.loaded / e.total) * 100)),
  }),
  verify: (id) => p(`upgrade-packages/${id}/verify/`),
  remove: (id) => d(`upgrade-packages/${id}/`),
  download: (pkg) => download(`upgrade-packages/${pkg.package_id}/download/`, {}, pkg.file_name),
}

export const tasks = {
  list: (q) => g('upgrade-tasks/', q),
  get: (id) => g(`upgrade-tasks/${id}/`),
  create: (data) => p('upgrade-tasks/', data),
  records: (id, q) => g(`upgrade-tasks/${id}/records/`, q),
  start: (id) => p(`upgrade-tasks/${id}/start/`),
  promote: (id) => p(`upgrade-tasks/${id}/promote/`),
  pause: (id, reason) => p(`upgrade-tasks/${id}/pause/`, { reason }),
  resume: (id) => p(`upgrade-tasks/${id}/resume/`),
  retryFailed: (id) => p(`upgrade-tasks/${id}/retry-failed/`),
  rollback: (id, data) => p(`upgrade-tasks/${id}/rollback/`, data),
}

export const records = {
  list: (q) => g('upgrade-records/', q),
}

export const audit = {
  list: (q) => g('operation-logs/', q),
  export: (q) => download('operation-logs/export/', clean(q), 'operation-logs.csv'),
}
