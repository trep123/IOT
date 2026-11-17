<template>
  <div class="page" v-loading="!b">
    <template v-if="b">
      <div class="card head">
        <div>
          <h2>批次 #{{ b.batch_id }} · {{ b.template_name }} <DictTag :dict="BATCH" :value="b.status" size="default" /></h2>
          <div class="muted">{{ scopeText(b.target_scope) }} · 离线策略：{{ OFFLINE_POLICY[b.offline_policy]?.label }} · 并发 {{ b.concurrency }} · 操作人 {{ b.operator_id }} · {{ fmtTime(b.created_at) }}
            <template v-if="b.retry_of"> · 重试自 <span class="link" @click="$router.push(`/batches/${b.retry_of}`)">#{{ b.retry_of }}</span></template></div>
          <div class="params">参数 <span class="mono">{{ JSON.stringify(b.params) }}</span></div>
        </div>
        <div>
          <el-popconfirm v-if="b.status === 'RUNNING'" title="取消尚未下发的指令？已在途的指令不受影响" width="260" @confirm="cancel">
            <template #reference><el-button type="danger" plain :icon="'CircleClose'">取消批次</el-button></template>
          </el-popconfirm>
          <el-button v-if="b.status !== 'RUNNING' && b.failed > 0" type="primary" :icon="'RefreshRight'" @click="retry">重试失败设备（{{ b.failed }}）</el-button>
        </div>
      </div>
      <div class="grid grid-4">
        <StatCard label="目标设备" :value="b.total" unit="台" icon="Monitor" />
        <StatCard label="执行成功" :value="b.success" unit="台" icon="CircleCheck" color="green" :hint="`成功率 ${pct(b.success_rate)}`" />
        <StatCard label="失败 / 超时" :value="b.failed" unit="台" icon="Warning" color="red" />
        <StatCard label="待执行" :value="b.pending" unit="台" icon="Loading" color="orange" :hint="b.cancelled ? `已取消 ${b.cancelled} 台` : ''" />
      </div>
      <div class="card">
        <div class="card-title">执行明细
          <el-radio-group v-model="filters.status__in" size="small" @change="search">
            <el-radio-button value="">全部</el-radio-button>
            <el-radio-button value="SUCCESS">成功</el-radio-button>
            <el-radio-button value="FAILED,TIMEOUT">失败 / 超时</el-radio-button>
            <el-radio-button value="PENDING,SENT,DELIVERED">进行中</el-radio-button>
            <el-radio-button value="CANCELLED">已取消</el-radio-button>
          </el-radio-group>
        </div>
        <el-table v-loading="loading" :data="rows" size="small">
          <el-table-column prop="command_id" label="指令 ID" width="90" />
          <el-table-column label="设备" min-width="140"><template #default="{ row }"><span class="link mono" @click="$router.push(`/devices/${row.device_id}`)">{{ row.device_id }}</span></template></el-table-column>
          <el-table-column label="状态" width="100"><template #default="{ row }"><DictTag :dict="COMMAND" :value="row.status" /></template></el-table-column>
          <el-table-column label="结果码" width="80" prop="result_code" />
          <el-table-column label="结果 / 错误" min-width="200" show-overflow-tooltip><template #default="{ row }"><span :class="{ err: row.error_msg }">{{ row.error_msg || (row.result_data ? JSON.stringify(row.result_data) : '—') }}</span></template></el-table-column>
          <el-table-column label="发送" width="170"><template #default="{ row }">{{ fmtTime(row.sent_at) }}</template></el-table-column>
          <el-table-column label="完成" width="170"><template #default="{ row }">{{ fmtTime(row.finished_at) }}</template></el-table-column>
        </el-table>
        <div class="pager"><el-pagination v-model:current-page="page" v-model:page-size="size" :total="total" layout="total, sizes, prev, pager, next" @change="load" /></div>
      </div>
    </template>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { batches } from '@/api'
import { BATCH, COMMAND, OFFLINE_POLICY } from '@/utils/dict'
import { fmtTime, pct, scopeText } from '@/utils/format'
import { useTable } from '@/utils/useTable'
import { useRealtimeRefresh } from '@/utils/useRealtimeRefresh'
import StatCard from '@/components/StatCard.vue'
import DictTag from '@/components/DictTag.vue'

const id = Number(useRoute().params.id)
const router = useRouter()
const b = ref(null)
const { filters, rows, total, loading, page, size, load, search } = useTable((q) => batches.commands(id, q), { status__in: '' }, { ordering: 'command_id' })
async function loadBatch() { b.value = await batches.get(id) }
async function cancel() { b.value = await batches.cancel(id); ElMessage.success('已取消未下发的指令'); load() }
async function retry() {
  const critical = rows.value[0]?.is_critical
  if (critical) await ElMessageBox.confirm(`关键指令：将对 ${b.value.failed} 台失败设备重新下发，确认？`, '二次确认', { type: 'warning' })
  const nb = await batches.retry(id, !!critical)
  ElMessage.success(`已创建重试批次 #${nb.batch_id}`)
  router.push(`/batches/${nb.batch_id}`)
}
onMounted(() => { loadBatch(); load() })
useRealtimeRefresh(['batch_update'], loadBatch, { filter: (d) => d.batch_id === id, wait: 300 })
useRealtimeRefresh(['command_update'], () => load(true), { filter: (d) => d.batch_id === id })
</script>
<style scoped>
.head .muted { font-size: 13px; }
.head h2 .mono { font-size: 18px; }
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.head h2 { margin: 0 0 6px; font-size: 20px; display: flex; align-items: center; gap: 10px; }
.params { margin-top: 6px; font-size: 13px; color: #475569; }
.err { color: #dc2626; }
</style>
