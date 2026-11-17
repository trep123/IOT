<template>
  <div class="page">
    <div class="page-head">
      <div><h2>运行总览</h2><p>设备在线情况、控制批次与升级任务的实时概况</p></div>
      <el-button :icon="'Refresh'" @click="load">刷新</el-button>
    </div>

    <div class="grid grid-4">
      <StatCard label="设备总数" :value="sum.total" unit="台" icon="Monitor" color="blue" :hint="`${sum.by_model?.length || 0} 种型号`" />
      <StatCard label="在线设备" :value="sum.online" unit="台" icon="CircleCheck" color="green" :hint="`在线率 ${onlineRate}`" />
      <StatCard label="离线设备" :value="sum.offline" unit="台" icon="CircleClose" color="gray" hint="超过心跳周期 × N 判定离线" />
      <StatCard label="进行中的升级任务" :value="activeTasks.length" unit="个" icon="Upload" color="orange" :hint="`执行中的批量控制 ${runningBatches.length} 个`" />
    </div>

    <div class="grid grid-3">
      <div class="card">
        <div class="card-title">在线状态</div>
        <EChart :option="onlineOpt" height="240px" />
      </div>
      <div class="card">
        <div class="card-title">型号分布</div>
        <EChart :option="modelOpt" height="240px" />
      </div>
      <div class="card">
        <div class="card-title">版本分布 <span class="sub">设备当前运行版本</span></div>
        <EChart :option="versionOpt" height="240px" />
      </div>
    </div>

    <div class="grid grid-2">
      <div class="card">
        <div class="card-title">升级任务 <el-button link type="primary" @click="$router.push('/tasks')">全部任务</el-button></div>
        <el-empty v-if="!taskList.length" :image-size="70" description="还没有升级任务" />
        <div v-for="t in taskList" :key="t.task_id" class="task" @click="$router.push(`/tasks/${t.task_id}`)">
          <div class="row">
            <span><b>#{{ t.task_id }}</b> <DictTag :dict="TASK_TYPE" :value="t.task_type" /> 目标版本 <span class="mono">{{ t.version_no }}</span></span>
            <DictTag :dict="TASK" :value="t.status" />
          </div>
          <el-progress :percentage="Math.round((t.stats.progress || 0) * 100)" :status="t.status === 'COMPLETED' ? 'success' : t.status === 'PAUSED' ? 'exception' : ''" :stroke-width="8" />
          <div class="meta muted">成功 {{ t.stats.success }} · 失败 {{ t.stats.failed }} · 共 {{ t.stats.total }} 台 · 失败率 {{ pct(t.stats.failure_rate) }} / 阈值 {{ pct(t.failure_threshold, 0) }}
            <span v-if="t.pause_reason" class="warn"> · {{ t.pause_reason }}</span></div>
        </div>
      </div>
      <div class="card">
        <div class="card-title">批量控制 <el-button link type="primary" @click="$router.push('/batches')">全部批次</el-button></div>
        <el-empty v-if="!batchList.length" :image-size="70" description="还没有批量控制" />
        <div v-for="b in batchList" :key="b.batch_id" class="task" @click="$router.push(`/batches/${b.batch_id}`)">
          <div class="row">
            <span><b>#{{ b.batch_id }}</b> {{ b.template_name }} <span class="muted mono">{{ b.template_code }}</span></span>
            <DictTag :dict="BATCH" :value="b.status" />
          </div>
          <el-progress :percentage="b.total ? Math.round(((b.success + b.failed + b.cancelled) / b.total) * 100) : 0" :stroke-width="8"
                       :status="b.status === 'COMPLETED' ? 'success' : b.status === 'PARTIAL_FAILED' ? 'warning' : ''" />
          <div class="meta muted">成功 {{ b.success }} · 失败 {{ b.failed }} · 待执行 {{ b.pending }} · 共 {{ b.total }} 台 · {{ fromNow(b.created_at) }}</div>
        </div>
      </div>
    </div>

    <div class="grid grid-2">
      <div class="card">
        <div class="card-title">最近状态变更 <el-button link type="primary" @click="$router.push('/status-logs')">全部记录</el-button></div>
        <el-table :data="logs" size="small">
          <el-table-column label="设备" min-width="120"><template #default="{ row }"><span class="link mono" @click="$router.push(`/devices/${row.device_id}`)">{{ row.device_id }}</span></template></el-table-column>
          <el-table-column label="变更" width="130"><template #default="{ row }"><DictTag :dict="ONLINE" :value="row.to_status" /></template></el-table-column>
          <el-table-column label="原因" width="110"><template #default="{ row }">{{ row.reason_display }}</template></el-table-column>
          <el-table-column label="时间" width="110"><template #default="{ row }">{{ fromNow(row.occurred_at) }}</template></el-table-column>
        </el-table>
      </div>
      <div class="card">
        <div class="card-title">实时事件 <span class="sub">来自 WebSocket 推送</span></div>
        <EventFeed :events="rt.events" :limit="12" />
      </div>
    </div>
  </div>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { devices, statusLogs, tasks, batches } from '@/api'
import { ONLINE, TASK, TASK_TYPE, BATCH } from '@/utils/dict'
import { fromNow, pct } from '@/utils/format'
import { useRealtime } from '@/stores/realtime'
import { useRealtimeRefresh } from '@/utils/useRealtimeRefresh'
import StatCard from '@/components/StatCard.vue'
import EChart from '@/components/EChart.vue'
import DictTag from '@/components/DictTag.vue'
import EventFeed from '@/components/EventFeed.vue'

const rt = useRealtime()
const sum = ref({ total: 0, online: 0, offline: 0, by_model: [], by_version: [] })
const taskList = ref([])
const batchList = ref([])
const logs = ref([])
const activeTasks = computed(() => taskList.value.filter((t) => ['GRAY', 'FULL', 'PAUSED', 'CREATED'].includes(t.status)))
const runningBatches = computed(() => batchList.value.filter((b) => b.status === 'RUNNING'))
const onlineRate = computed(() => (sum.value.total ? pct(sum.value.online / sum.value.total) : '—'))

const palette = ['#2563eb', '#16a34a', '#f59e0b', '#7c3aed', '#0891b2', '#db2777', '#64748b']
const onlineOpt = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  color: ['#22c55e', '#cbd5e1'],
  series: [{ type: 'pie', radius: ['55%', '78%'], center: ['50%', '45%'], label: { show: true, position: 'center', formatter: () => `${onlineRate.value}\n在线率`, fontSize: 16, fontWeight: 600, lineHeight: 22 },
    data: [{ name: '在线', value: sum.value.online }, { name: '离线', value: sum.value.offline }] }],
}))
const modelOpt = computed(() => ({
  tooltip: { trigger: 'item' }, color: palette, legend: { bottom: 0, type: 'scroll' },
  series: [{ type: 'pie', radius: '65%', center: ['50%', '45%'], label: { formatter: '{b}\n{c} 台' }, data: sum.value.by_model.map((m) => ({ name: m.model, value: m.count })) }],
}))
const versionOpt = computed(() => ({
  tooltip: { trigger: 'axis' }, grid: { left: 40, right: 16, top: 16, bottom: 30 },
  xAxis: { type: 'category', data: sum.value.by_version.map((v) => v.current_version || '未知') },
  yAxis: { type: 'value', minInterval: 1 },
  series: [{ type: 'bar', barMaxWidth: 36, itemStyle: { color: '#2563eb', borderRadius: [4, 4, 0, 0] }, data: sum.value.by_version.map((v) => v.count) }],
}))

async function load() {
  const [s, t, b, l] = await Promise.all([
    devices.summary(), tasks.list({ page_size: 5, ordering: '-task_id' }), batches.list({ page_size: 5, ordering: '-batch_id' }),
    statusLogs.list({ page_size: 8, ordering: '-occurred_at' }),
  ])
  sum.value = s
  taskList.value = t.results
  batchList.value = b.results
  logs.value = l.results
}
onMounted(load)
useRealtimeRefresh(['device_status', 'device_version', 'task_update', 'batch_update'], load, { wait: 1500 })
</script>
<style scoped>
.task { padding: 12px; border-radius: 8px; border: 1px solid #eef2f7; margin-bottom: 10px; cursor: pointer; transition: border-color .15s, background .15s; }
.task:hover { border-color: #bfdbfe; background: #f8fbff; }
.row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; gap: 8px; }
.meta { font-size: 12px; margin-top: 6px; }
.warn { color: #dc2626; }
</style>
