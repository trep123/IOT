<template>
  <el-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)" title="新建批量控制" width="720px" destroy-on-close @open="init">
    <el-steps :active="step" finish-status="success" simple class="steps">
      <el-step title="选择指令" /><el-step title="目标范围" /><el-step title="执行策略" />
    </el-steps>
    <el-form label-width="110px">
      <div v-show="step === 0">
        <el-form-item label="指令" required>
          <el-select v-model="templateId" placeholder="选择指令模板" filterable style="width: 100%">
            <el-option v-for="t in list" :key="t.template_id" :value="t.template_id" :label="`${t.name}（${t.code}）`">
              <span>{{ t.name }} <span class="muted mono">{{ t.code }}</span></span>
              <el-tag v-if="t.is_critical" type="danger" size="small" style="margin-left: 8px">关键</el-tag>
            </el-option>
          </el-select>
        </el-form-item>
        <template v-if="tpl">
          <el-form-item label="适用型号"><span class="muted">{{ !tpl.applicable_models?.length || tpl.applicable_models.includes('*') ? '全部型号' : tpl.applicable_models.join('、') }}</span></el-form-item>
          <ParamForm :schema="tpl.param_schema" :model="params" />
        </template>
      </div>
      <div v-show="step === 1">
        <el-form-item label="目标范围" required><ScopePicker ref="scopeRef" v-model="scope" /></el-form-item>
      </div>
      <div v-show="step === 2">
        <el-form-item label="离线设备">
          <el-radio-group v-model="offlinePolicy">
            <el-radio value="REJECT">直接标记失败</el-radio>
            <el-radio value="QUEUE">排队，上线后补发</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="并发上限">
          <el-input-number v-model="concurrency" :min="1" :max="1000" controls-position="right" />
          <span class="muted" style="margin-left: 10px">同时在途的指令数，完成一台补位一台</span>
        </el-form-item>
        <el-descriptions :column="1" border size="small" class="summary">
          <el-descriptions-item label="指令">{{ tpl?.name }}（{{ tpl?.code }}）</el-descriptions-item>
          <el-descriptions-item label="参数"><span class="mono">{{ JSON.stringify(previewParams) }}</span></el-descriptions-item>
          <el-descriptions-item label="目标">{{ scopeText(scope) }}<template v-if="scopeRef?.count !== null && scopeRef?.count !== undefined">，共 {{ scopeRef.count }} 台</template></el-descriptions-item>
        </el-descriptions>
        <el-alert v-if="tpl?.is_critical" type="error" :closable="false" show-icon style="margin-top: 12px" title="关键指令批量下发：提交时需要再次确认" />
      </div>
    </el-form>
    <template #footer>
      <el-button v-if="step > 0" @click="step--">上一步</el-button>
      <el-button v-if="step < 2" type="primary" @click="next">下一步</el-button>
      <el-button v-else type="primary" :loading="sending" @click="submit">提交批量控制</el-button>
    </template>
  </el-dialog>
</template>
<script setup>
import { computed, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { batches, templates } from '@/api'
import { collectParams, scopeError } from '@/utils/params'
import { scopeText } from '@/utils/format'
import ParamForm from './ParamForm.vue'
import ScopePicker from './ScopePicker.vue'

const props = defineProps({ modelValue: Boolean, deviceIds: Array })
const emit = defineEmits(['update:modelValue', 'created'])
const step = ref(0)
const list = ref([])
const templateId = ref(null)
const params = reactive({})
const scope = ref({ device_ids: [] })
const scopeRef = ref()
const offlinePolicy = ref('REJECT')
const concurrency = ref(20)
const sending = ref(false)
const tpl = computed(() => list.value.find((t) => t.template_id === templateId.value))
const previewParams = computed(() => { try { return collectParams(tpl.value?.param_schema, params) } catch { return {} } })

async function init() {
  step.value = 0
  templateId.value = null
  scope.value = { device_ids: props.deviceIds ? [...props.deviceIds] : [] }
  list.value = (await templates.all()).filter((t) => !t.is_system)
}
function next() {
  if (step.value === 0) {
    if (!tpl.value) return ElMessage.warning('请选择指令')
    try { collectParams(tpl.value.param_schema, params) } catch (e) { return ElMessage.warning(e.message) }
  }
  if (step.value === 1) {
    const err = scopeError(scope.value)
    if (err) return ElMessage.warning(err)
    if (scopeRef.value?.count === 0) return ElMessage.warning('当前范围没有匹配的设备')
  }
  step.value++
}
async function submit() {
  if (tpl.value.is_critical) {
    await ElMessageBox.confirm(`将对 ${scopeRef.value?.count ?? '多'} 台设备批量下发关键指令「${tpl.value.name}」，确认执行？`, '关键操作二次确认',
      { type: 'warning', confirmButtonText: '确认下发', confirmButtonClass: 'el-button--danger' })
  }
  sending.value = true
  try {
    const b = await batches.create({
      template_id: templateId.value, params: previewParams.value, target_scope: scope.value,
      offline_policy: offlinePolicy.value, concurrency: concurrency.value, confirm: !!tpl.value.is_critical,
    })
    ElMessage.success(`批次 #${b.batch_id} 已创建，共 ${b.total} 台`)
    emit('update:modelValue', false)
    emit('created', b)
  } finally { sending.value = false }
}
</script>
<style scoped>
.steps { margin-bottom: 20px; }
.summary { margin-top: 6px; }
</style>
