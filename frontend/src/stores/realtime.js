import { defineStore } from 'pinia'
import { getToken } from '@/api/http'

const handlers = new Map() // event -> Set<fn>
let ws = null
let retry = 0
let timer = null
let manualClose = false

/**
 * 管理端实时推送（ws/admin/）。页面通过 useRealtime().on(event, fn) 订阅，
 * 返回的函数用于取消订阅；断线后指数退避重连。
 */
export const useRealtime = defineStore('realtime', {
  state: () => ({ connected: false, events: [] }),
  actions: {
    connect() {
      const token = getToken()
      if (!token || (ws && ws.readyState <= 1)) return
      manualClose = false
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/ws/admin/?token=${encodeURIComponent(token)}`)
      ws.onopen = () => { this.connected = true; retry = 0 }
      ws.onclose = () => {
        this.connected = false
        ws = null
        if (manualClose) return
        clearTimeout(timer)
        timer = setTimeout(() => this.connect(), Math.min(30000, 1000 * 2 ** retry++))
      }
      ws.onmessage = (e) => {
        let msg
        try { msg = JSON.parse(e.data) } catch { return }
        if (!msg?.event) return
        this.events.unshift({ ...msg, at: Date.now() })
        if (this.events.length > 100) this.events.length = 100
        for (const key of [msg.event, '*']) handlers.get(key)?.forEach((fn) => fn(msg.data, msg.event))
      }
    },
    disconnect() {
      manualClose = true
      clearTimeout(timer)
      ws?.close()
      ws = null
      this.connected = false
    },
    on(event, fn) {
      if (!handlers.has(event)) handlers.set(event, new Set())
      handlers.get(event).add(fn)
      return () => handlers.get(event)?.delete(fn)
    },
  },
})
