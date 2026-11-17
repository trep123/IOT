import { onMounted, onBeforeUnmount } from 'vue'
import { useRealtime } from '@/stores/realtime'

/**
 * 订阅若干实时事件，事件到达后节流执行 fn（例如刷新列表），组件卸载时自动取消。
 * filter(data, event) 返回 false 时忽略该事件。
 */
export function useRealtimeRefresh(events, fn, { wait = 800, filter } = {}) {
  const rt = useRealtime()
  let offs = []
  let t = null
  const trigger = (data, event) => {
    if (filter && filter(data, event) === false) return
    if (t) return
    t = setTimeout(() => { t = null; fn(data, event) }, wait)
  }
  onMounted(() => { offs = events.map((e) => rt.on(e, trigger)) })
  onBeforeUnmount(() => { offs.forEach((off) => off()); clearTimeout(t) })
}
