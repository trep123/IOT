<template>
  <div class="page" v-loading="!t">
    <template v-if="t">
      <div class="card head">
        <div>
          <h2>{{ t.task_type === 'ROLLBACK' ? '回滚' : '升级' }}任务 #{{ t.task_id }} → <span class="mono">{{ t.version_no }}</span> <DictTag :dict="TASK" :value="t.status" size="default" /></h2>
          <div class="muted">{{ scopeText(t.target_scope) }} · 灰度 {{ pct(t.gray_ratio, 0) }} · 失败率阈值 {{ pct(t.failure_threshold, 0) }} · 操作人 {{ t.operator_id }} · {{ fmtTime(t.created_at) }}
            <template v-if="t.parent_task_id"> · 回滚自 <span class="link" @click="$router.push(`/tasks/${t.parent_task_id}`)">#{{ t.parent_task_id }}</span></template></div>
        </div>
        <div class="actions">
          <el-button v-if="t.status === 'CREATED'" type="primary" :icon="'VideoPlay'" @click="act('start', '开始灰度')">开始灰度</el-button>
          <el-button v-if="t.status === 'GRAY'" type="primary" :icon="'Top'" :disabled="grayRunning" @click="promote">推进全量</el-button>
          <el-button v-if="['GRAY', 'FULL'].includes(t.status)" type="warning" plain :icon="'VideoPause'" @click="pause">暂停</el-button>
          <el-button v-if="t.status === 'PAUSED'" type="success" :icon="'VideoPlay'" @click="act('resume', '继续')">继续</el-button>
          <el-button v-if="t.stats.failed > 0 && t.status !== 'ROLLED_BACK'" :icon="'RefreshRight'" @click="act('retryFailed', '重试失败设备')">重试失败（{{ t.stats.failed }}）</el-button>
          <el-button v-if="t.task_type === 'UPGRADE' && t.status !== 'ROLLED_BACK' && t.status !== 'CREATED'" type="danger" plain :icon="'RefreshLeft'" @click="openRollback">回滚</el-button>
        </div>
      </div>

      <el-alert v-if="t.status === 'PAUSED'" type="error" show-icon :closable="false" :title="`任务已暂停：${t.pause_reason || '人工暂停'}`"
                description="确认问题后可「继续」（已发生的失败视为已确认，不再计入熔断），或回滚到旧版本。" />
      <el-alert v-else-if="t.status === 'GRAY' && !grayRunning" type="success" show-icon :closable="false"
                :title="`灰度完成：${t.stats.gray.success} 台成功，${t.stats.gray.failed} 台失败。确认无误后可推进全量。`" />

      <div class="card">
        <el-steps :active="flowStep" finish-status="success" align-center>
          <el-step title="已创建" :description="fmtTime(t.created_at)" />
          <el-step title="灰度发布" :description="`${t.stats.gray.total} 台`" :status="t.status === 'PAUSED' && pausedAt === 'GRAY' ? 'error' : undefined" />
          <el-step title="全量发布" :description="`${t.stats.total - t.stats.gray.total} 台`" :status="t.status === 'PAUSED' && pausedAt === 'FULL' ? 'error' : undefined" />
          <el-step :title="t.status === 'ROLLED_BACK' ? '已回滚' : '完成'" :description="fmtTime(t.finished_at)" :status="t.status === 'ROLLED_BACK' ? 'error' : undefined" />
        </el-steps>
      </div>

      <div class="grid grid-4">
        <StatCard label="纳入设备" :value="t.stats.total" unit="台" icon="Monitor" :hint="t.excluded?.length ? `自动排除 ${t.excluded.length} 台` : '无排除设备'" />
        <StatCard label="升级成功" :value="t.stats.success" unit="台" icon="CircleCheck" color="green" :hint="`整体进度 ${pct(t.stats.progress)}`" />
        <StatCard label="升级失败" :value="t.stats.failed" unit="台" icon="Warning" color="red" :hint="`失败率 ${pct(t.stats.failure_rate)} / 阈值 ${pct(t.failure_threshold, 0)}`" />
        <StatCard label="进行中 / 等待" :value="`${t.stats.in_progress} / ${t.stats.waiting}`" icon="Loading" color="orange" />
      </div>

      <div class="grid grid-2">
        <div class="card">
          <div class="card-title">阶段分布</div>
          <EChart :option="stageOpt" height="220px" />
        </div>
        <div class="card">
          <div class="card-title">自动排除的设备 <span class="sub">{{ t.excluded?.length || 0 }} 台</span></div>
          <el-table :data="t.excluded || []" size="small" max-height="220" empty-text="没有被排除的设备">
            <el-table-column label="设备" min-width="130"><template #default="{ row }"><span class="mono">{{ row.device_id }}</span></template></el-table-column>
            <el-table-column label="原因" min-width="180" prop="reason" show-overflow-tooltip />
          </el-table>
        </div>
      </div>

      <div class="card">
        <div class="card-title">逐台升级记录
          <div class="filters">
            <el-radio-group v-model="filters.phase" size="small" @change="search">
              <el-radio-button value="">全部</el-radio-button><el-radio-button value="GRAY">灰度</el-radio-button><el-radio-button value="FULL">全量</el-radio-button>
            </el-radio-group>
            <el-select v-model="filters.stage" size="small" placeholder="阶段" clearable style="width: 120px" @change="search"><el-option v-for="o in options(STAGE)" :key="o.value" v-bind="o" /></el-select>
            <el-input v-model="filters.device_id" size="small" placeholder="设备编号" clearable style="width: 150px" @keyup.enter="search" @clear="search" />
          </div>
        </div>
        <el-table v-loading="loading" :data="rows" size="small">
          <el-table-column label="设备" min-width="150"><template #default="{ row }"><span class="link mono" @click="$router.push(`/devices/${row.device_id}`)">{{ row.device_id }}</span> <span class="muted">{{ row.device_name }}</span></template></el-table-column>
          <el-table-column label="阶段" width="80"><template #default="{ row }"><DictTag :dict="PHASE" :value="row.phase" /></template></el-table-column>
          <el-table-column label="版本" width="150"><template #default="{ row }"><span class="mono">{{ row.from_version || '—' }} → {{ row.to_version }}</span></template></el-table-column>
          <el-table-column label="升级包" width="80"><template #default="{ row }">{{ row.package_id ? `#${row.package_id}` : '—' }}</template></el-table-column>
          <el-table-column label="进度" min-width="230"><template #default="{ row }"><UpgradeProgress :record="row" /></template></el-table-column>
          <el-table-column label="重试" width="60" prop="retry_count" />
          <el-table-column label="错误" min-width="160" show-overflow-tooltip><template #default="{ row }"><span class="err">{{ row.error_msg }}</span></template></el-table-column>
          <el-table-column label="阶段更新" width="170"><template #default="{ row }">{{ fmtTime(row.stage_changed_at) }}</template></el-table-column>
        </el-table>
        <div class="pager"><el-pagination v-model:current-page="page" v-model:page-size="size" :total="total" :page-sizes="[20, 50, 100]" layout="total, sizes, prev, pager, next" @change="load" /></div>
      </div>
    </template>

    <el-dialog v-model="rbDlg" title="版本回滚" width="520px">
      <el-alert type="warning" :closable="false" show-icon title="将暂停/结束当前任务，并为已升级的设备创建回滚任务" style="margin-bottom: 14px" />
      <el-form label-width="110px">
        <el-form-item label="回滚到版本" required>
          <el-select v-model="rb.target_version_id" placeholder="更旧的可发布版本" style="width: 100%">
            <el-option v-for="v in olderVersions" :key="v.version_id" :value="v.version_id" :label="v.version_no" />
          </el-select>
        </el-form-item>
        <el-form-item label="灰度比例"><el-slider v-model="rb.grayPct" :min="1" :max="100" style="width: 260px" /><span style="margin-left: 12px">{{ rb.grayPct }}%</span></el-form-item>
        <el-form-item label="失败率阈值"><el-input-number v-model="rb.thresholdPct" :min="0" :max="100" controls-position="right" /> <span class="muted" style="margin-left: 8px">%</span></el-form-item>
      </el-form>
      <template #footer><el-button @click="rbDlg = false">取消</el-button><el-button type="danger" @click="rollback">确认回滚</el-button></template>
    </el-dialog>
  </div>
</template>
<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { tasks, versions } from '@/api'
import { TASK, PHASE, STAGE, STAGE_ORDER, options } from '@/utils/dict'
import { fmtTime, pct, scopeText } from '@/utils/format'
import { useTable } from '@/utils/useTable'
import { useRealtimeRefresh } from '@/utils/useRealtimeRefresh'
import StatCard from '@/components/StatCard.vue'
import DictTag from '@/components/DictTag.vue'
import EChart from '@/components/EChart.vue'
import UpgradeProgress from '@/components/UpgradeProgress.vue'

const id = Number(useRoute().params.id)
const router = useRouter()
const t = ref(null)
const { filters, rows, total, loading, page, size, load, search } = useTable((q) => tasks.records(id, q), { phase: '', stage: '', device_id: '' })
const pausedAt = ref('')
const grayRunning = computed(() => { const g = t.value?.stats.gray; return g ? g.success + g.failed < g.total : false })
const flowStep = computed(() => ({ CREATED: 1, GRAY: 1, FULL: 2, PAUSED: pausedAt.value === 'FULL' ? 2 : 1, COMPLETED: 4, ROLLED_BACK: 3 }[t.value?.status] ?? 0))

const COLORS = { WAITING: '#cbd5e1', DOWNLOADING: '#60a5fa', VERIFYING: '#3b82f6', INSTALLING: '#2563eb', REBOOTING: '#f59e0b', SUCCESS: '#22c55e', FAILED: '#ef4444' }
const stageOpt = computed(() => {
  const by = t.value?.stats.by_stage || {}
  const keys = [...STAGE_ORDER, 'FAILED']
  return {
    tooltip: { trigger: 'axis' }, grid: { left: 40, right: 16, top: 16, bottom: 30 },
    xAxis: { type: 'category', data: keys.map((k) => STAGE[k].label) }, yAxis: { type: 'value', minInterval: 1 },
    series: [{ type: 'bar', barMaxWidth: 34, data: keys.map((k) => ({ value: by[k] || 0, itemStyle: { color: COLORS[k], borderRadius: [4, 4, 0, 0] } })) }],
  }
})

async function loadTask() {
  t.value = await tasks.get(id)
  pausedAt.value = t.value.status === 'PAUSED' ? t.value.paused_from : ''
}
async function act(name, label) { t.value = await tasks[name](id); ElMessage.success(`${label}：已执行`); load() }
async function promote() {
  const g = t.value.stats.gray
  await ElMessageBox.confirm(`灰度结果：成功 ${g.success} 台，失败 ${g.failed} 台。确认推进到全量（${t.value.stats.total - g.total} 台）？`, '推进全量', { type: 'warning' })
  await act('promote', '推进全量')
}
async function pause() {
  const { value } = await ElMessageBox.prompt('暂停原因（可选）', '暂停升级', { inputPlaceholder: '如：发现兼容性问题' })
  t.value = await tasks.pause(id, value || ''); ElMessage.success('已暂停')
}
const rbDlg = ref(false)
const allVersions = ref([])
const rb = reactive({ target_version_id: null, grayPct: 100, thresholdPct: 20 })
const olderVersions = computed(() => {
  const cur = t.value?.version_no
  const cmp = (a, b) => { const x = a.split('.').map(Number), y = b.split('.').map(Number); for (let i = 0; i < Math.max(x.length, y.length); i++) { const d = (x[i] || 0) - (y[i] || 0); if (d) return d } return 0 }
  return allVersions.value.filter((v) => v.status === 'RELEASABLE' && cur && cmp(v.version_no, cur) < 0)
})
async function openRollback() { allVersions.value = await versions.all(); rb.target_version_id = olderVersions.value.at(-1)?.version_id ?? null; rbDlg.value = true }
async function rollback() {
  if (!rb.target_version_id) return ElMessage.warning('请选择回滚版本')
  const r = await tasks.rollback(id, { target_version_id: rb.target_version_id, gray_ratio: rb.grayPct / 100, failure_threshold: rb.thresholdPct / 100 })
  rbDlg.value = false
  if (r.rollback_task) { ElMessage.success(`已创建回滚任务 #${r.rollback_task.task_id}`); router.push(`/tasks/${r.rollback_task.task_id}`) }
  else { ElMessage.info('没有需要回滚的设备，任务已标记为已回滚'); t.value = r.task }
}
onMounted(async () => { await load(); loadTask() })
useRealtimeRefresh(['task_update'], loadTask, { filter: (d) => d.task_id === id, wait: 400 })
useRealtimeRefresh(['upgrade_record'], () => load(true), { filter: (d) => d.task_id === id, wait: 600 })
</script>
<style scoped>
.head .muted { font-size: 13px; }
.head h2 .mono { font-size: 18px; }
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.head h2 { margin: 0 0 6px; font-size: 20px; display: flex; align-items: center; gap: 10px; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }
.actions .el-button { margin-left: 0; }
.filters { display: flex; gap: 8px; align-items: center; }
.err { color: #dc2626; }
</style>
