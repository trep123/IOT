<template>
  <div class="page" v-loading="!dev">
    <template v-if="dev">
      <div class="card head">
        <div class="title">
          <div class="avatar" :class="dev.online_status"><el-icon><Cpu /></el-icon></div>
          <div>
            <h2>{{ dev.name }} <DictTag :dict="ONLINE" :value="dev.online_status" size="default" dot /></h2>
            <div class="muted"><span class="mono">{{ dev.device_id }}</span> · {{ dev.model }} · 版本 <span class="mono">{{ dev.current_version || '—' }}</span> · {{ dev.group_name || '未分组' }}</div>
          </div>
        </div>
        <div>
          <el-button :icon="'Key'" @click="showSecret">接入密钥</el-button>
          <el-button type="primary" :icon="'Promotion'" @click="cmdOpen = true">下发指令</el-button>
        </div>
      </div>

      <div class="grid grid-4">
        <StatCard label="最近心跳" :value="fromNow(dev.last_heartbeat_at)" icon="Timer" :hint="fmtTime(dev.last_heartbeat_at)" />
        <StatCard label="最近上线" :value="fromNow(dev.last_online_at)" icon="CircleCheck" color="green" :hint="fmtTime(dev.last_online_at)" />
        <StatCard label="最近离线" :value="fromNow(dev.last_offline_at)" icon="CircleClose" color="gray" :hint="fmtTime(dev.last_offline_at)" />
        <StatCard label="建档时间" :value="fmtTime(dev.created_at).slice(0, 10)" icon="Calendar" color="purple" :hint="fmtTime(dev.created_at)" />
      </div>

      <div class="card">
        <el-tabs v-model="tab">
          <el-tab-pane label="指令记录" name="commands">
            <el-table :data="cmds.rows" v-loading="cmds.loading" size="small">
              <el-table-column prop="command_id" label="ID" width="80" />
              <el-table-column label="指令" min-width="160"><template #default="{ row }">{{ row.template_name }} <span class="muted mono">{{ row.template_code }}</span> <el-tag v-if="row.is_critical" type="danger" size="small">关键</el-tag></template></el-table-column>
              <el-table-column label="参数" min-width="160" show-overflow-tooltip><template #default="{ row }"><span class="mono">{{ JSON.stringify(row.params) }}</span></template></el-table-column>
              <el-table-column label="状态" width="100"><template #default="{ row }"><DictTag :dict="COMMAND" :value="row.status" /></template></el-table-column>
              <el-table-column label="结果" min-width="160" show-overflow-tooltip><template #default="{ row }">{{ row.error_msg || (row.result_data ? JSON.stringify(row.result_data) : row.result_code ?? '—') }}</template></el-table-column>
              <el-table-column label="批次" width="80"><template #default="{ row }"><span v-if="row.batch_id" class="link" @click="$router.push(`/batches/${row.batch_id}`)">#{{ row.batch_id }}</span><span v-else class="muted">单发</span></template></el-table-column>
              <el-table-column label="操作人" width="90" prop="operator_id" />
              <el-table-column label="创建时间" width="170"><template #default="{ row }">{{ fmtTime(row.created_at) }}</template></el-table-column>
            </el-table>
            <div class="pager"><el-pagination v-model:current-page="cmds.page" :total="cmds.total" :page-size="10" layout="total, prev, pager, next" @current-change="loadCmds" /></div>
          </el-tab-pane>
          <el-tab-pane label="状态变更" name="logs">
            <el-timeline v-if="logs.rows.length" class="timeline">
              <el-timeline-item v-for="l in logs.rows" :key="l.log_id" :timestamp="fmtTime(l.occurred_at)" :type="l.to_status === 'ONLINE' ? 'success' : 'info'" placement="top">
                <b>{{ l.to_status === 'ONLINE' ? '上线' : '离线' }}</b>（{{ l.reason_display }}）<span class="muted">· 上一状态持续 {{ fmtDuration(l.duration_seconds) }}</span>
              </el-timeline-item>
            </el-timeline>
            <el-empty v-else :image-size="60" description="暂无状态变更" />
            <div class="pager"><el-pagination v-model:current-page="logs.page" :total="logs.total" :page-size="10" layout="total, prev, pager, next" @current-change="loadLogs" /></div>
          </el-tab-pane>
          <el-tab-pane label="升级记录" name="upgrades">
            <el-table :data="ups.rows" size="small">
              <el-table-column label="任务" width="80"><template #default="{ row }"><span class="link" @click="$router.push(`/tasks/${row.task_id}`)">#{{ row.task_id }}</span></template></el-table-column>
              <el-table-column label="版本" width="160"><template #default="{ row }"><span class="mono">{{ row.from_version || '—' }} → {{ row.to_version }}</span></template></el-table-column>
              <el-table-column label="阶段" width="90"><template #default="{ row }"><DictTag :dict="PHASE" :value="row.phase" /></template></el-table-column>
              <el-table-column label="进度" min-width="200"><template #default="{ row }"><UpgradeProgress :record="row" /></template></el-table-column>
              <el-table-column label="错误" min-width="140" show-overflow-tooltip prop="error_msg" />
              <el-table-column label="更新时间" width="170"><template #default="{ row }">{{ fmtTime(row.updated_at) }}</template></el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </div>
    </template>

    <el-dialog v-model="secretOpen" title="设备接入密钥" width="520px">
      <el-descriptions :column="1" border>
        <el-descriptions-item label="接入地址"><span class="mono">ws://&lt;host&gt;/ws/device/{{ id }}/?secret=…</span></el-descriptions-item>
        <el-descriptions-item label="密钥"><span class="mono">{{ secret }}</span> <el-button link type="primary" @click="copy">复制</el-button></el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-popconfirm title="重置后旧密钥立即失效，设备需要用新密钥重新接入" width="260" @confirm="reset">
          <template #reference><el-button type="danger" plain>重置密钥</el-button></template>
        </el-popconfirm>
        <el-button type="primary" @click="secretOpen = false">关闭</el-button>
      </template>
    </el-dialog>
    <CommandDialog v-model="cmdOpen" :device-id="id" @sent="loadCmds" />
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { devices, commands, records } from '@/api'
import { ONLINE, COMMAND, PHASE } from '@/utils/dict'
import { fmtTime, fromNow, fmtDuration } from '@/utils/format'
import { useRealtimeRefresh } from '@/utils/useRealtimeRefresh'
import StatCard from '@/components/StatCard.vue'
import DictTag from '@/components/DictTag.vue'
import CommandDialog from '@/components/CommandDialog.vue'
import UpgradeProgress from '@/components/UpgradeProgress.vue'

const id = useRoute().params.id
const dev = ref(null)
const tab = ref('commands')
const cmds = reactive({ rows: [], total: 0, page: 1, loading: false })
const logs = reactive({ rows: [], total: 0, page: 1 })
const ups = reactive({ rows: [] })
const cmdOpen = ref(false)
const secretOpen = ref(false)
const secret = ref('')

async function loadDev() { dev.value = await devices.get(id) }
async function loadCmds() {
  cmds.loading = true
  try { const r = await commands.list({ device_id: id, page: cmds.page, page_size: 10, ordering: '-command_id' }); cmds.rows = r.results; cmds.total = r.count } finally { cmds.loading = false }
}
async function loadLogs() { const r = await devices.statusLogs(id, { page: logs.page, page_size: 10 }); logs.rows = r.results; logs.total = r.count }
async function loadUps() { ups.rows = (await records.list({ device_id: id, page_size: 50, ordering: '-record_id' })).results }
async function showSecret() { secret.value = (await devices.secret(id)).secret; secretOpen.value = true }
async function reset() { secret.value = (await devices.resetSecret(id)).secret; ElMessage.success('密钥已重置') }
function copy() { navigator.clipboard?.writeText(secret.value); ElMessage.success('已复制') }

onMounted(() => Promise.all([loadDev(), loadCmds(), loadLogs(), loadUps()]))
const mine = (d) => d.device_id === id
useRealtimeRefresh(['device_status', 'device_version'], () => { loadDev(); loadLogs() }, { filter: mine, wait: 300 })
useRealtimeRefresh(['command_update'], loadCmds, { filter: mine, wait: 300 })
useRealtimeRefresh(['upgrade_record'], loadUps, { filter: mine, wait: 300 })
</script>
<style scoped>
.head .muted { font-size: 13px; }
.head h2 .mono { font-size: 18px; }
.head { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
.title { display: flex; gap: 16px; align-items: center; }
.title h2 { margin: 0 0 4px; font-size: 20px; display: flex; align-items: center; gap: 10px; }
.avatar { width: 52px; height: 52px; border-radius: 14px; display: grid; place-items: center; font-size: 26px; background: #f1f5f9; color: #64748b; }
.avatar.ONLINE { background: #dcfce7; color: #16a34a; }
.timeline { padding: 8px 4px 0; }
</style>
