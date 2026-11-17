<template>
  <div class="page">
    <div class="page-head">
      <div><h2>升级任务</h2><p>灰度 → 人工确认 → 全量；失败率超阈值自动暂停；异常时回滚到旧版本</p></div>
      <el-button type="primary" :icon="'Plus'" @click="openCreate()">创建升级任务</el-button>
    </div>
    <div class="card">
      <div class="toolbar">
        <el-select v-model="filters.status" placeholder="状态" clearable @change="search"><el-option v-for="o in options(TASK)" :key="o.value" v-bind="o" /></el-select>
        <el-select v-model="filters.task_type" placeholder="类型" clearable @change="search"><el-option v-for="o in options(TASK_TYPE)" :key="o.value" v-bind="o" /></el-select>
        <el-select v-model="filters.version_id" placeholder="目标版本" clearable @change="search"><el-option v-for="v in allVersions" :key="v.version_id" :value="v.version_id" :label="v.version_no" /></el-select>
        <el-button type="primary" @click="search">查询</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" class="clickable" @row-click="(r) => $router.push(`/tasks/${r.task_id}`)">
        <el-table-column label="任务" width="80"><template #default="{ row }"><b>#{{ row.task_id }}</b></template></el-table-column>
        <el-table-column label="类型" width="80"><template #default="{ row }"><DictTag :dict="TASK_TYPE" :value="row.task_type" /></template></el-table-column>
        <el-table-column label="目标版本" width="110"><template #default="{ row }"><span class="mono">{{ row.version_no }}</span></template></el-table-column>
        <el-table-column label="范围" min-width="140"><template #default="{ row }">{{ scopeText(row.target_scope) }}</template></el-table-column>
        <el-table-column label="进度" min-width="220"><template #default="{ row }">
          <el-progress :percentage="Math.round((row.stats.progress || 0) * 100)" :status="row.status === 'COMPLETED' ? 'success' : row.status === 'PAUSED' ? 'exception' : ''" />
          <div class="nums muted">成功 {{ row.stats.success }} · 失败 {{ row.stats.failed }} · 进行中 {{ row.stats.in_progress }} · 等待 {{ row.stats.waiting }} / {{ row.stats.total }}</div>
        </template></el-table-column>
        <el-table-column label="失败率 / 阈值" width="120"><template #default="{ row }"><span :class="{ danger: row.stats.failure_rate > row.failure_threshold }">{{ pct(row.stats.failure_rate) }}</span> / {{ pct(row.failure_threshold, 0) }}</template></el-table-column>
        <el-table-column label="灰度比例" width="90"><template #default="{ row }">{{ pct(row.gray_ratio, 0) }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><DictTag :dict="TASK" :value="row.status" /></template></el-table-column>
        <el-table-column label="创建时间" width="170"><template #default="{ row }">{{ fmtTime(row.created_at) }}</template></el-table-column>
      </el-table>
      <div class="pager"><el-pagination v-model:current-page="page" v-model:page-size="size" :total="total" layout="total, prev, pager, next" @change="load" /></div>
    </div>

    <el-dialog v-model="dlg" title="创建升级任务" width="680px" destroy-on-close>
      <el-form label-width="110px">
        <el-form-item label="目标版本" required>
          <el-select v-model="form.version_id" placeholder="选择可发布版本" style="width: 100%">
            <el-option v-for="v in releasable" :key="v.version_id" :value="v.version_id" :label="`${v.version_no}（${v.applicable_models.join('、')}）`" />
          </el-select>
          <div v-if="ver" class="muted hint">适用型号 {{ ver.applicable_models.join('、') }}；最低可升级版本 {{ ver.min_upgradable_version || '不限' }}。不满足条件、已是目标版本或已在其他任务中的设备会被自动排除。</div>
        </el-form-item>
        <el-form-item label="目标范围" required><ScopePicker v-model="form.target_scope" /></el-form-item>
        <el-form-item label="灰度比例">
          <el-slider v-model="grayPct" :min="1" :max="100" :format-tooltip="(v) => v + '%'" style="width: 300px; margin-right: 16px" />
          <span>{{ grayPct }}%<span class="muted">{{ grayPct === 100 ? '（跳过灰度直接全量）' : '' }}</span></span>
        </el-form-item>
        <el-form-item label="指定灰度设备"><DevicePicker v-model="form.gray_device_ids" multiple placeholder="可选：优先作为灰度设备" /></el-form-item>
        <el-form-item label="失败率阈值">
          <el-input-number v-model="thresholdPct" :min="0" :max="100" controls-position="right" /><span class="muted" style="margin-left: 8px">% ，超过后自动暂停</span>
        </el-form-item>
        <el-form-item label="立即开始"><el-switch v-model="form.start" /><span class="muted" style="margin-left: 8px">创建后直接开始灰度</span></el-form-item>
      </el-form>
      <template #footer><el-button @click="dlg = false">取消</el-button><el-button type="primary" :loading="saving" @click="create">创建</el-button></template>
    </el-dialog>
  </div>
</template>
<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { tasks, versions } from '@/api'
import { TASK, TASK_TYPE, options } from '@/utils/dict'
import { fmtTime, pct, scopeText } from '@/utils/format'
import { useTable } from '@/utils/useTable'
import { scopeError } from '@/utils/params'
import { useRealtimeRefresh } from '@/utils/useRealtimeRefresh'
import DictTag from '@/components/DictTag.vue'
import ScopePicker from '@/components/ScopePicker.vue'
import DevicePicker from '@/components/DevicePicker.vue'

const route = useRoute()
const router = useRouter()
const { filters, rows, total, loading, page, size, load, search } = useTable(tasks.list, { status: '', task_type: '', version_id: '' }, { ordering: '-task_id' })
const allVersions = ref([])
const releasable = computed(() => allVersions.value.filter((v) => v.status === 'RELEASABLE'))
const dlg = ref(false)
const saving = ref(false)
const form = reactive({ version_id: null, target_scope: { device_ids: [] }, gray_device_ids: [], start: true })
const grayPct = ref(10)
const thresholdPct = ref(20)
const ver = computed(() => allVersions.value.find((v) => v.version_id === form.version_id))

function openCreate(versionId) {
  Object.assign(form, { version_id: versionId || null, target_scope: { device_ids: [] }, gray_device_ids: [], start: true })
  grayPct.value = 10; thresholdPct.value = 20; dlg.value = true
}
async function create() {
  if (!form.version_id) return ElMessage.warning('请选择目标版本')
  const err = scopeError(form.target_scope)
  if (err) return ElMessage.warning(err)
  saving.value = true
  try {
    const t = await tasks.create({ ...form, gray_ratio: grayPct.value / 100, failure_threshold: thresholdPct.value / 100 })
    ElMessage.success(`任务 #${t.task_id} 已创建，纳入 ${t.stats.total} 台${t.excluded?.length ? `，自动排除 ${t.excluded.length} 台` : ''}`)
    dlg.value = false
    router.push(`/tasks/${t.task_id}`)
  } finally { saving.value = false }
}
onMounted(async () => {
  load()
  allVersions.value = await versions.all()
  if (route.query.create) openCreate(Number(route.query.create))
})
useRealtimeRefresh(['task_update'], () => load(true))
</script>
<style scoped>
.clickable :deep(tr) { cursor: pointer; }
.nums { font-size: 12px; }
.danger { color: #dc2626; font-weight: 600; }
.hint { font-size: 12px; line-height: 1.6; margin-top: 4px; }
</style>
