<template>
  <div class="scope">
    <el-radio-group v-model="mode" @change="emitValue">
      <el-radio-button value="device_ids">指定设备</el-radio-button>
      <el-radio-button value="group_id">按分组</el-radio-button>
      <el-radio-button value="filters">按条件</el-radio-button>
      <el-radio-button value="all">全部设备</el-radio-button>
    </el-radio-group>
    <div class="body">
      <DevicePicker v-if="mode === 'device_ids'" v-model="ids" multiple @update:model-value="emitValue" />
      <el-select v-else-if="mode === 'group_id'" v-model="groupId" placeholder="选择分组" style="width: 100%" @change="emitValue">
        <el-option v-for="g in groupList" :key="g.group_id" :value="g.group_id" :label="`${g.name}（${g.device_count ?? 0} 台）`" />
      </el-select>
      <div v-else-if="mode === 'filters'" class="filters">
        <el-select v-model="f.model" placeholder="型号" clearable filterable @change="emitValue">
          <el-option v-for="m in models" :key="m" :value="m" :label="m" />
        </el-select>
        <el-select v-model="f.version" placeholder="当前版本" clearable filterable @change="emitValue">
          <el-option v-for="v in versionList" :key="v" :value="v" :label="v || '（无）'" />
        </el-select>
        <el-select v-model="f.group_id" placeholder="分组" clearable @change="emitValue">
          <el-option v-for="g in groupList" :key="g.group_id" :value="g.group_id" :label="g.name" />
        </el-select>
        <el-select v-model="f.online_status" placeholder="在线状态" clearable @change="emitValue">
          <el-option value="ONLINE" label="仅在线" /><el-option value="OFFLINE" label="仅离线" />
        </el-select>
      </div>
      <el-alert v-else type="warning" :closable="false" show-icon title="将作用于平台全部设备，请谨慎操作" />
      <div class="preview">
        <el-icon><InfoFilled /></el-icon>
        <span v-if="count === null">正在统计目标设备…</span>
        <span v-else>当前范围匹配 <b>{{ count }}</b> 台设备<template v-if="online !== null">，其中在线 <b class="ok">{{ online }}</b> 台</template></span>
      </div>
    </div>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { devices, groups } from '@/api'
import DevicePicker from './DevicePicker.vue'

const props = defineProps({ modelValue: Object })
const emit = defineEmits(['update:modelValue'])
const mode = ref('device_ids')
const ids = ref([])
const groupId = ref(null)
const f = reactive({ model: '', version: '', group_id: '', online_status: '' })
const groupList = ref([])
const models = ref([])
const versionList = ref([])
const count = ref(null)
const online = ref(null)

function build() {
  if (mode.value === 'device_ids') return { device_ids: ids.value }
  if (mode.value === 'group_id') return { group_id: groupId.value }
  if (mode.value === 'all') return { all: true }
  const filters = {}
  for (const [k, v] of Object.entries(f)) if (v !== '' && v !== null && v !== undefined) filters[k] = v
  return { filters }
}
let t
function emitValue() {
  const v = build()
  emit('update:modelValue', v)
  clearTimeout(t)
  t = setTimeout(() => preview(v), 250)
}
async function preview(v) {
  count.value = null
  online.value = null
  let q = {}
  if (v.device_ids) { if (!v.device_ids.length) { count.value = 0; online.value = 0; return } q = { device_id__in: v.device_ids.join(',') } }
  else if (v.group_id) q = { group_id: v.group_id }
  else if (v.group_id === null) { count.value = 0; online.value = 0; return }
  else if (v.filters) q = { ...v.filters }
  const s = await devices.summary(q)
  count.value = s.total
  online.value = s.online
}
onMounted(async () => {
  const [gs, s] = await Promise.all([groups.all(), devices.summary()])
  groupList.value = gs
  models.value = s.by_model.map((x) => x.model)
  versionList.value = s.by_version.map((x) => x.current_version)
  if (props.modelValue?.device_ids) ids.value = [...props.modelValue.device_ids]
  emitValue()
})
watch(() => props.modelValue, (v) => {
  if (v?.device_ids && JSON.stringify(v.device_ids) !== JSON.stringify(ids.value)) { mode.value = 'device_ids'; ids.value = [...v.device_ids]; preview(v) }
})
defineExpose({ count })
</script>
<style scoped>
.scope { width: 100%; }
.body { margin-top: 10px; display: flex; flex-direction: column; gap: 10px; }
.filters { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
.preview { font-size: 13px; color: #475569; display: flex; align-items: center; gap: 6px; background: #f8fafc; padding: 6px 10px; border-radius: 6px; }
.preview b { color: #2563eb; }
.preview b.ok { color: #16a34a; }
</style>
