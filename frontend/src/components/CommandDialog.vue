<template>
  <el-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)" title="下发控制指令" width="620px" destroy-on-close @open="init">
    <el-form label-width="110px" :model="form">
      <el-form-item label="目标设备" required>
        <DevicePicker v-model="form.device_id" :multiple="false" />
      </el-form-item>
      <el-form-item label="指令" required>
        <el-select v-model="form.template_id" placeholder="选择指令模板" filterable style="width: 100%">
          <el-option v-for="t in usable" :key="t.template_id" :value="t.template_id" :label="`${t.name}（${t.code}）`">
            <span>{{ t.name }} <span class="muted mono">{{ t.code }}</span></span>
            <el-tag v-if="t.is_critical" type="danger" size="small" style="margin-left: 8px">关键</el-tag>
          </el-option>
        </el-select>
      </el-form-item>
      <template v-if="tpl">
        <el-alert v-if="tpl.is_critical" type="error" :closable="false" show-icon class="mb"
                  title="关键操作：下发前需要二次确认，下发与执行结果都会写入操作审计" />
        <ParamForm :schema="tpl.param_schema" :model="params" />
        <el-form-item label="离线时">
          <el-radio-group v-model="form.offline_policy">
            <el-radio value="REJECT">直接拒绝</el-radio>
            <el-radio value="QUEUE">排队，上线后下发</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="超时"><span class="muted">{{ tpl.timeout_seconds }} 秒内无结果判定为超时</span></el-form-item>
      </template>
    </el-form>
    <template v-if="result">
      <el-divider>执行结果</el-divider>
      <div class="result">
        <DictTag :dict="COMMAND" :value="result.status" size="default" />
        <span class="muted">指令 #{{ result.command_id }}</span>
        <el-icon v-if="!TERMINAL.includes(result.status)" class="is-loading"><Loading /></el-icon>
        <span v-if="result.result_code !== null && result.result_code !== undefined">结果码 {{ result.result_code }}</span>
        <span v-if="result.error_msg" class="err">{{ result.error_msg }}</span>
      </div>
      <pre v-if="result.result_data" class="json">{{ JSON.stringify(result.result_data, null, 2) }}</pre>
    </template>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">关闭</el-button>
      <el-button type="primary" :loading="sending" :disabled="!form.device_id || !form.template_id" @click="send">
        {{ tpl?.is_critical ? '确认并下发' : '下发' }}
      </el-button>
    </template>
  </el-dialog>
</template>
<script setup>
import { computed, reactive, ref, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { commands, devices, templates } from '@/api'
import { COMMAND } from '@/utils/dict'
import { collectParams } from '@/utils/params'
import { useRealtime } from '@/stores/realtime'
import DevicePicker from './DevicePicker.vue'
import ParamForm from './ParamForm.vue'
import DictTag from './DictTag.vue'

const props = defineProps({ modelValue: Boolean, deviceId: String })
const emit = defineEmits(['update:modelValue', 'sent'])
const TERMINAL = ['SUCCESS', 'FAILED', 'TIMEOUT', 'CANCELLED']
const list = ref([])
const device = ref(null)
const form = reactive({ device_id: '', template_id: null, offline_policy: 'REJECT' })
const params = reactive({})
const sending = ref(false)
const result = ref(null)
const tpl = computed(() => list.value.find((t) => t.template_id === form.template_id))
const usable = computed(() => list.value.filter((t) => !t.is_system &&
  (!device.value || !t.applicable_models?.length || t.applicable_models.includes('*') || t.applicable_models.includes(device.value.model))))

const rt = useRealtime()
const off = rt.on('command_update', (d) => { if (result.value && d.command_id === result.value.command_id) result.value = { ...result.value, ...d } })
onBeforeUnmount(off)

async function init() {
  result.value = null
  form.device_id = props.deviceId || ''
  form.template_id = null
  list.value = await templates.all()
  device.value = props.deviceId ? await devices.get(props.deviceId) : null
}

async function send() {
  let p
  try { p = collectParams(tpl.value.param_schema, params) } catch (e) { return ElMessage.warning(e.message) }
  if (tpl.value.is_critical) {
    await ElMessageBox.confirm(`将向设备 ${form.device_id} 下发关键指令「${tpl.value.name}」，参数 ${JSON.stringify(p)}。确认执行？`,
      '关键操作二次确认', { type: 'warning', confirmButtonText: '确认下发', confirmButtonClass: 'el-button--danger' })
  }
  sending.value = true
  try {
    result.value = await commands.create({ ...form, params: p, confirm: !!tpl.value.is_critical })
    ElMessage.success('指令已提交')
    emit('sent', result.value)
  } finally { sending.value = false }
}
</script>
<style scoped>
.mb { margin-bottom: 14px; }
.result { display: flex; gap: 12px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
.err { color: #dc2626; }
</style>
