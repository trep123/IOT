<template>
  <div class="page">
    <div class="page-head">
      <div><h2>设备列表</h2><p>设备档案与在线状态；状态由心跳维护，变化会实时刷新</p></div>
      <div>
        <el-button :icon="'Download'" @click="devices.export(filters)">导出 CSV</el-button>
        <el-button type="primary" :icon="'Plus'" @click="openCreate">新建设备</el-button>
      </div>
    </div>

    <div class="grid grid-4">
      <StatCard label="当前筛选设备" :value="sum.total" unit="台" icon="Monitor" />
      <StatCard label="在线" :value="sum.online" unit="台" icon="CircleCheck" color="green" />
      <StatCard label="离线" :value="sum.offline" unit="台" icon="CircleClose" color="gray" />
      <StatCard label="在线率" :value="sum.total ? ((sum.online / sum.total) * 100).toFixed(1) : '—'" unit="%" icon="TrendCharts" color="purple" />
    </div>

    <div class="card">
      <div class="toolbar">
        <el-input v-model="filters.search" placeholder="设备编号 / 名称" clearable :prefix-icon="'Search'" @keyup.enter="refresh" @clear="refresh" />
        <el-select v-model="filters.online_status" placeholder="在线状态" clearable @change="refresh">
          <el-option value="ONLINE" label="在线" /><el-option value="OFFLINE" label="离线" />
        </el-select>
        <el-select v-model="filters.model" placeholder="型号" clearable filterable @change="refresh">
          <el-option v-for="m in sum.by_model" :key="m.model" :value="m.model" :label="`${m.model}（${m.count}）`" />
        </el-select>
        <el-select v-model="filters.group_id" placeholder="分组" clearable @change="refresh">
          <el-option v-for="g in groupList" :key="g.group_id" :value="g.group_id" :label="g.name" />
        </el-select>
        <el-select v-model="filters.version" placeholder="当前版本" clearable filterable @change="refresh">
          <el-option v-for="v in sum.by_version" :key="v.current_version" :value="v.current_version" :label="`${v.current_version || '未知'}（${v.count}）`" />
        </el-select>
        <el-date-picker v-model="onlineRange" type="datetimerange" start-placeholder="最近上线起" end-placeholder="止" style="width: 340px" @change="refresh" />
        <el-button type="primary" @click="refresh">查询</el-button>
        <el-button @click="resetAll">重置</el-button>
        <div class="grow" />
        <el-button :disabled="!selected.length" :icon="'Operation'" @click="batchOpen = true">批量控制（{{ selected.length }}）</el-button>
      </div>

      <el-table v-loading="loading" :data="rows" @selection-change="(s) => (selected = s)" @sort-change="onSort" row-key="device_id">
        <el-table-column type="selection" width="44" />
        <el-table-column prop="device_id" label="设备编号" min-width="140" sortable="custom">
          <template #default="{ row }"><span class="link mono" @click="$router.push(`/devices/${row.device_id}`)">{{ row.device_id }}</span></template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="140" sortable="custom" show-overflow-tooltip />
        <el-table-column prop="model" label="型号" width="110" sortable="custom" />
        <el-table-column label="分组" width="120"><template #default="{ row }">{{ row.group_name || '—' }}</template></el-table-column>
        <el-table-column prop="current_version" label="当前版本" width="110" sortable="custom"><template #default="{ row }"><span class="mono">{{ row.current_version || '—' }}</span></template></el-table-column>
        <el-table-column prop="online_status" label="状态" width="90" sortable="custom"><template #default="{ row }"><DictTag :dict="ONLINE" :value="row.online_status" dot /></template></el-table-column>
        <el-table-column label="最近心跳" width="120"><template #default="{ row }"><el-tooltip :content="fmtTime(row.last_heartbeat_at)"><span>{{ fromNow(row.last_heartbeat_at) }}</span></el-tooltip></template></el-table-column>
        <el-table-column prop="last_online_at" label="最近上线" width="170" sortable="custom"><template #default="{ row }">{{ fmtTime(row.last_online_at) }}</template></el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openCommand(row)">下发指令</el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-popconfirm :title="`删除设备 ${row.device_id}？其指令与升级记录会一并删除`" width="260" @confirm="remove(row)">
              <template #reference><el-button link type="danger">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager">
        <el-pagination v-model:current-page="page" v-model:page-size="size" :total="total" :page-sizes="[20, 50, 100, 200]" layout="total, sizes, prev, pager, next, jumper" @change="load" />
      </div>
    </div>

    <el-dialog v-model="editOpen" :title="editing ? `编辑设备 ${form.device_id}` : '新建设备'" width="520px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="设备编号" prop="device_id"><el-input v-model="form.device_id" :disabled="editing" placeholder="字母、数字、-、_" /></el-form-item>
        <el-form-item label="名称" prop="name"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="型号" prop="model">
          <el-select v-model="form.model" filterable allow-create default-first-option placeholder="选择或输入型号" style="width: 100%">
            <el-option v-for="m in sum.by_model" :key="m.model" :value="m.model" :label="m.model" />
          </el-select>
        </el-form-item>
        <el-form-item label="分组"><el-select v-model="form.group_id" clearable placeholder="不分组" style="width: 100%"><el-option v-for="g in groupList" :key="g.group_id" :value="g.group_id" :label="g.name" /></el-select></el-form-item>
        <el-form-item label="当前版本"><el-input v-model="form.current_version" placeholder="如 1.0.0，设备上报后自动更新" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="secretOpen" title="设备已创建" width="520px">
      <el-alert type="warning" :closable="false" show-icon title="请妥善保存接入密钥，设备连接 ws/device/<编号>/?secret=… 时使用；可在设备详情中重置" />
      <el-descriptions :column="1" border style="margin-top: 14px">
        <el-descriptions-item label="设备编号"><span class="mono">{{ created?.device_id }}</span></el-descriptions-item>
        <el-descriptions-item label="接入密钥"><span class="mono">{{ created?.secret }}</span>
          <el-button link type="primary" :icon="'CopyDocument'" @click="copy(created?.secret)">复制</el-button></el-descriptions-item>
      </el-descriptions>
      <template #footer><el-button type="primary" @click="secretOpen = false">我已保存</el-button></template>
    </el-dialog>

    <CommandDialog v-model="cmdOpen" :device-id="cmdDevice" />
    <BatchDialog v-model="batchOpen" :device-ids="selected.map((d) => d.device_id)" @created="(b) => $router.push(`/batches/${b.batch_id}`)" />
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute } from 'vue-router'
import { devices, groups } from '@/api'
import { ONLINE } from '@/utils/dict'
import { fmtTime, fromNow } from '@/utils/format'
import { useTable } from '@/utils/useTable'
import { useRealtimeRefresh } from '@/utils/useRealtimeRefresh'
import StatCard from '@/components/StatCard.vue'
import DictTag from '@/components/DictTag.vue'
import CommandDialog from '@/components/CommandDialog.vue'
import BatchDialog from '@/components/BatchDialog.vue'

const { filters, rows, total, loading, page, size, load, search, onSort } = useTable(
  (q) => devices.list({ ...q, ...range() }),
  { search: '', online_status: '', model: '', group_id: '', version: '' }, { ordering: 'device_id' })
const route = useRoute()
const onlineRange = ref(null)
const range = () => (onlineRange.value ? { last_online_after: onlineRange.value[0].toISOString(), last_online_before: onlineRange.value[1].toISOString() } : {})
const sum = ref({ total: 0, online: 0, offline: 0, by_model: [], by_version: [] })
const groupList = ref([])
const selected = ref([])

async function loadSummary() {
  const q = { ...filters, ...range() }
  for (const k of Object.keys(q)) if (q[k] === '' || q[k] === null) delete q[k]
  sum.value = await devices.summary(q)
}
function refresh() { search(); loadSummary() }
function resetAll() { for (const k of Object.keys(filters)) filters[k] = ''; onlineRange.value = null; refresh() }

const editOpen = ref(false)
const editing = ref(false)
const saving = ref(false)
const formRef = ref()
const form = reactive({ device_id: '', name: '', model: '', group_id: null, current_version: '' })
const rules = {
  device_id: [{ required: true, message: '必填' }, { pattern: /^[A-Za-z0-9_-]+$/, message: '仅允许字母、数字、-、_' }],
  name: [{ required: true, message: '必填' }],
  model: [{ required: true, message: '必填' }],
}
const secretOpen = ref(false)
const created = ref(null)

function openCreate() { editing.value = false; Object.assign(form, { device_id: '', name: '', model: '', group_id: null, current_version: '' }); editOpen.value = true }
function openEdit(row) { editing.value = true; Object.assign(form, { device_id: row.device_id, name: row.name, model: row.model, group_id: row.group_id, current_version: row.current_version }); editOpen.value = true }
async function save() {
  await formRef.value.validate()
  saving.value = true
  try {
    if (editing.value) {
      const { device_id, ...rest } = form
      await devices.update(device_id, rest)
      ElMessage.success('已保存')
    } else {
      created.value = await devices.create({ ...form })
      secretOpen.value = true
    }
    editOpen.value = false
    refresh()
  } finally { saving.value = false }
}
async function remove(row) { await devices.remove(row.device_id); ElMessage.success('已删除'); refresh() }
function copy(t) { navigator.clipboard?.writeText(t); ElMessage.success('已复制') }

const cmdOpen = ref(false)
const cmdDevice = ref('')
function openCommand(row) { cmdDevice.value = row.device_id; cmdOpen.value = true }
const batchOpen = ref(false)

onMounted(async () => {
  groupList.value = await groups.all()
  if (route.query.group_id) filters.group_id = Number(route.query.group_id)
  if (route.query.online_status) filters.online_status = route.query.online_status
  refresh()
})
useRealtimeRefresh(['device_status', 'device_version'], () => { load(true); loadSummary() }, { wait: 1000 })
</script>
