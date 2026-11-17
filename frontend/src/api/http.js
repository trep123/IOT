import axios from 'axios'
import { ElMessage } from 'element-plus'

const TOKEN_KEY = 'iot_token'
export const getToken = () => localStorage.getItem(TOKEN_KEY) || ''
export const setToken = (t) => (t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY))

const http = axios.create({ baseURL: '/api/', timeout: 30000 })

http.interceptors.request.use((cfg) => {
  const t = getToken()
  if (t) cfg.headers.Authorization = `Token ${t}`
  return cfg
})

/** 把 DRF 标准错误（{detail} 或 {字段: [原因]}）整理成一句话 */
export function drfError(err) {
  const data = err?.response?.data
  if (!data) return err?.message || '网络错误'
  if (typeof data === 'string') return data.slice(0, 200)
  if (data.detail) return String(data.detail)
  const parts = []
  for (const [k, v] of Object.entries(data)) {
    const msg = Array.isArray(v) ? v.join('；') : typeof v === 'object' ? JSON.stringify(v) : v
    parts.push(k === 'non_field_errors' ? msg : `${k}：${msg}`)
  }
  return parts.join('\n') || `请求失败（${err.response.status}）`
}

http.interceptors.response.use(
  (r) => r,
  (err) => {
    const status = err?.response?.status
    if (status === 401 || (status === 403 && !getToken())) {
      setToken('')
      if (!location.pathname.endsWith('/login')) location.href = '/login'
    } else if (!err.config?.silent) {
      ElMessage({ type: 'error', message: drfError(err), duration: 4000, showClose: true })
    }
    return Promise.reject(err)
  },
)

/** 下载 CSV 等文件：带上 Token，生成临时链接触发保存 */
export async function download(url, params, filename) {
  const r = await http.get(url, { params, responseType: 'blob' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(r.data)
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}

export default http
