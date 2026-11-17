<template>
  <div class="feed">
    <el-empty v-if="!list.length" :image-size="60" description="暂无事件，设备上下线、指令和升级进度会实时出现在这里" />
    <div v-for="(e, i) in list" :key="e.at + '-' + i" class="item">
      <el-tag size="small" :type="meta(e).type" effect="light" class="tag">{{ meta(e).label }}</el-tag>
      <span class="text">{{ describe(e) }}</span>
      <span class="time">{{ time(e.at) }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import dayjs from 'dayjs'
import { COMMAND, STAGE, TASK, BATCH, STATUS_REASON } from '@/utils/dict'

const props = defineProps({ events: { type: Array, default: () => [] }, limit: { type: Number, default: 50 } })
const list = computed(() => props.events.slice(0, props.limit))
const time = (t) => dayjs(t).format('HH:mm:ss')

const META = {
  device_status: { label: '在线状态', type: 'success' },
  device_version: { label: '版本变化', type: 'primary' },
  command_update: { label: '指令', type: '' },
  batch_update: { label: '批量控制', type: 'warning' },
  task_update: { label: '升级任务', type: 'danger' },
  upgrade_record: { label: '升级进度', type: 'info' },
}
const meta = (e) => META[e.event] || { label: e.event, type: 'info' }

function describe({ event, data = {} }) {
  switch (event) {
    case 'device_status':
      return `${data.device_id} ${data.online_status === 'ONLINE' ? '上线' : '离线'}${data.reason ? `（${STATUS_REASON[data.reason]?.label || data.reason}）` : ''}`
    case 'device_version':
      return `${data.device_id} 当前版本 ${data.current_version || '—'}`
    case 'command_update':
      return `#${data.command_id} ${data.device_id || ''} ${data.template_code || ''} ${COMMAND[data.status]?.label || data.status}`
    case 'batch_update':
      return `批次 #${data.batch_id} ${BATCH[data.status]?.label || data.status || ''} 成功 ${data.success ?? '-'} / 失败 ${data.failed ?? '-'} / 共 ${data.total ?? '-'}`
    case 'task_update':
      return `任务 #${data.task_id} ${TASK[data.status]?.label || data.status}，进度 ${Math.round((data.progress || 0) * 100)}%${data.pause_reason ? `，${data.pause_reason}` : ''}`
    case 'upgrade_record':
      return `${data.device_id} ${STAGE[data.stage]?.label || data.stage} ${data.progress ?? ''}%${data.error_msg ? `，${data.error_msg}` : ''}`
    default:
      return JSON.stringify(data).slice(0, 80)
  }
}
</script>

<style scoped>
.feed { max-height: 360px; overflow-y: auto; }
.item { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px dashed #eef2f7; font-size: 13px; }
.tag { flex: none; width: 70px; justify-content: center; }
.text { flex: 1; color: #334155; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.time { color: #94a3b8; font-variant-numeric: tabular-nums; flex: none; }
</style>
