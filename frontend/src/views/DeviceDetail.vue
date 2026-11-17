<template>
  <div class="page" v-loading="!dev">
    <template v-if="dev">
      <div class="card head">
        <div class="title">
          <div class="avatar" :class="dev.online_status"><el-icon><Cpu /></el-icon></div>
          <div>
            <h2>{{ dev.name }} <DictTag :dict="ONLINE" :value="dev.online_status" size="default" dot />
              <el-tag :type="dev.has_key ? 'success' : 'warning'" effect="plain" class="clickable" @click="keyOpen = true">{{ dev.has_key ? '接入 Key 已生成' : '未生成接入 Key' }}</el-tag></h2>
            <div class="muted"><span class="mono">{{ dev.device_id }}</span> · {{ dev.model }} · 版本 <span class="mono">{{ dev.current_version || '—' }}</span> · {{ dev.group_name || '未分组' }}</div>
          </div>
        </div>
        <div>
          <el-button :icon="'QuestionFilled'" @click="$router.push({ path: '/help/device-access', query: { device: id } })">接入示例</el-button>
          <el-button :icon="'Key'" :type="dev.has_key ? '' : 'warning'" @click="keyOpen = true">接入 Key</el-button>
          <el-button type="primary" :icon="'Promotion'" @click="cmdOpen = true">下发指令</el-button>
        </div>
      </div>

      <el-alert v-if="!dev.has_key" type="warning" show-icon :closable="false"
        title="该设备尚未生成接入 Key，无法上线。点击右上角「接入 Key」手动生成后烧录到设备。" />
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

    <KeyDialog v-model="keyOpen" :device-id="id" @changed="loadDev" />
    <CommandDialog v-model="cmdOpen" :device-id="id" @sent="loadCmds" />
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { devices, commands, records } from '@/api'
import { ONLINE, COMMAND, PHASE } from '@/utils/dict'
import { fmtTime, fromNow, fmtDuration } from '@/utils/format'
import { useRealtimeRefresh } from '@/utils/useRealtimeRefresh'
import StatCard from '@/components/StatCard.vue'
import DictTag from '@/components/DictTag.vue'
import CommandDialog from '@/components/CommandDialog.vue'
import UpgradeProgress from '@/components/UpgradeProgress.vue'
import KeyDialog from '@/components/KeyDialog.vue'

const id = useRoute().params.id
const dev = ref(null)
const tab = ref('commands')
const cmds = reactive({ rows: [], total: 0, page: 1, loading: false })
const logs = reactive({ rows: [], total: 0, page: 1 })
const ups = reactive({ rows: [] })
const cmdOpen = ref(false)
const keyOpen = ref(false)

async function loadDev() { dev.value = await devices.get(id) }
async function loadCmds() {
  cmds.loading = true
  try { const r = await commands.list({ device_id: id, page: cmds.page, page_size: 10, ordering: '-command_id' }); cmds.rows = r.results; cmds.total = r.count } finally { cmds.loading = false }
}
async function loadLogs() { const r = await devices.statusLogs(id, { page: logs.page, page_size: 10 }); logs.rows = r.results; logs.total = r.count }
async function loadUps() { ups.rows = (await records.list({ device_id: id, page_size: 50, ordering: '-record_id' })).results }

onMounted(() => Promise.all([loadDev(), loadCmds(), loadLogs(), loadUps()]))
const mine = (d) => d.device_id === id
useRealtimeRefresh(['device_status', 'device_version', 'device_key'], () => { loadDev(); loadLogs() }, { filter: mine, wait: 300 })
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
