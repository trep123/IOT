<template>
  <el-dialog :model-value="modelValue" :title="`设备接入 Key · ${deviceId}`" width="600px" @update:model-value="close" @open="load">
    <div v-loading="loading">
      <template v-if="info.secret">
        <el-alert type="warning" :closable="false" show-icon
          title="接入 Key 等同于设备密码，请仅烧录到对应设备；泄露后请立即重新生成或吊销。" />
        <el-descriptions :column="1" border class="desc">
          <el-descriptions-item label="设备编号"><span class="mono">{{ deviceId }}</span></el-descriptions-item>
          <el-descriptions-item label="接入 Key">
            <span class="mono key">{{ info.secret }}</span>
            <el-button link type="primary" :icon="'CopyDocument'" @click="copy(info.secret)">复制</el-button>
          </el-descriptions-item>
          <el-descriptions-item label="生成时间">{{ fmtTime(info.key_created_at) }}</el-descriptions-item>
          <el-descriptions-item label="接入地址">
            <span class="mono small">{{ wsBase }}/ws/device/{{ deviceId }}/?ts=…&amp;nonce=…&amp;sign=…</span>
          </el-descriptions-item>
          <el-descriptions-item label="签名方式">
            <span class="mono small">sign = hex(HMAC-SHA256(Key, "{{ deviceId }}\n" + ts + "\n" + nonce))</span>
          </el-descriptions-item>
        </el-descriptions>
      </template>
      <el-result v-else icon="warning" title="尚未生成接入 Key" sub-title="设备必须使用管理员手动生成的 Key 签名后才能上线。">
        <template #extra>
          <el-button type="primary" :icon="'Key'" :loading="busy" @click="generate">生成接入 Key</el-button>
        </template>
      </el-result>
    </div>
    <template #footer>
      <div class="footer">
        <el-button link type="primary" :icon="'QuestionFilled'" @click="toHelp">查看接入示例（Python / C / C++ / Java）</el-button>
        <div>
          <template v-if="info.secret">
            <el-popconfirm title="吊销后设备立即下线，且在重新生成前无法上线" width="260" @confirm="revoke">
              <template #reference><el-button type="danger" plain :loading="busy">吊销</el-button></template>
            </el-popconfirm>
            <el-popconfirm title="重新生成后旧 Key 立即失效，当前连接会被断开" width="260" @confirm="generate">
              <template #reference><el-button type="warning" plain :loading="busy">重新生成</el-button></template>
            </el-popconfirm>
          </template>
          <el-button type="primary" @click="close(false)">关闭</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { devices } from '@/api'
import { fmtTime } from '@/utils/format'
import { copyText as copy } from '@/utils/clipboard'

const props = defineProps({ modelValue: Boolean, deviceId: { type: String, default: '' } })
const emit = defineEmits(['update:modelValue', 'changed'])
const router = useRouter()
const loading = ref(false)
const busy = ref(false)
const info = reactive({ secret: null, key_created_at: null })
const wsBase = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`

async function load() {
  loading.value = true
  try { Object.assign(info, await devices.secret(props.deviceId)) } finally { loading.value = false }
}
async function generate() {
  busy.value = true
  try {
    Object.assign(info, await devices.generateKey(props.deviceId))
    ElMessage.success('已生成新的接入 Key')
    emit('changed')
  } finally { busy.value = false }
}
async function revoke() {
  busy.value = true
  try {
    Object.assign(info, await devices.revokeKey(props.deviceId))
    ElMessage.success('接入 Key 已吊销')
    emit('changed')
  } finally { busy.value = false }
}
function close() { emit('update:modelValue', false) }
function toHelp() { close(); router.push({ path: '/help/device-access', query: { device: props.deviceId } }) }
</script>

<style scoped>
.desc { margin-top: 14px; }
.key { font-size: 15px; letter-spacing: 0.5px; margin-right: 6px; }
.small { font-size: 12px; word-break: break-all; }
.footer { display: flex; justify-content: space-between; align-items: center; }
</style>
