<template>
  <div class="page">
    <div class="page-head">
      <div><h2>批量控制</h2><p>按设备列表 / 分组 / 条件批量下发，按并发上限补位执行，失败设备可一键重试</p></div>
      <el-button type="primary" :icon="'Plus'" @click="open = true">新建批量控制</el-button>
    </div>
    <div class="card">
      <div class="toolbar">
        <el-select v-model="filters.status" placeholder="状态" clearable @change="search"><el-option v-for="o in options(BATCH)" :key="o.value" v-bind="o" /></el-select>
        <el-select v-model="filters.template_id" placeholder="指令" clearable @change="search"><el-option v-for="t in tpls" :key="t.template_id" :value="t.template_id" :label="t.name" /></el-select>
        <el-button type="primary" @click="search">查询</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" @row-click="(r) => $router.push(`/batches/${r.batch_id}`)" class="clickable">
        <el-table-column prop="batch_id" label="批次" width="80"><template #default="{ row }"><b>#{{ row.batch_id }}</b></template></el-table-column>
        <el-table-column label="指令" min-width="170"><template #default="{ row }">{{ row.template_name }} <span class="muted mono">{{ row.template_code }}</span></template></el-table-column>
        <el-table-column label="目标" min-width="150"><template #default="{ row }">{{ scopeText(row.target_scope) }}<span v-if="row.retry_of" class="muted">（重试 #{{ row.retry_of }}）</span></template></el-table-column>
        <el-table-column label="进度" min-width="220">
          <template #default="{ row }">
            <div class="bar">
              <span class="ok" :style="{ width: w(row, 'success') }" /><span class="bad" :style="{ width: w(row, 'failed') }" /><span class="can" :style="{ width: w(row, 'cancelled') }" />
            </div>
            <div class="nums muted">成功 {{ row.success }} · 失败 {{ row.failed }} · 待执行 {{ row.pending }}<template v-if="row.cancelled"> · 取消 {{ row.cancelled }}</template> / {{ row.total }}</div>
          </template>
        </el-table-column>
        <el-table-column label="成功率" width="90"><template #default="{ row }">{{ pct(row.success_rate) }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><DictTag :dict="BATCH" :value="row.status" /></template></el-table-column>
        <el-table-column label="离线策略" width="110"><template #default="{ row }">{{ OFFLINE_POLICY[row.offline_policy]?.label }}</template></el-table-column>
        <el-table-column prop="operator_id" label="操作人" width="90" />
        <el-table-column label="创建时间" width="170"><template #default="{ row }">{{ fmtTime(row.created_at) }}</template></el-table-column>
      </el-table>
      <div class="pager"><el-pagination v-model:current-page="page" v-model:page-size="size" :total="total" layout="total, sizes, prev, pager, next" @change="load" /></div>
    </div>
    <BatchDialog v-model="open" @created="(b) => $router.push(`/batches/${b.batch_id}`)" />
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { batches, templates } from '@/api'
import { BATCH, OFFLINE_POLICY, options } from '@/utils/dict'
import { fmtTime, pct, scopeText } from '@/utils/format'
import { useTable } from '@/utils/useTable'
import { useRealtimeRefresh } from '@/utils/useRealtimeRefresh'
import DictTag from '@/components/DictTag.vue'
import BatchDialog from '@/components/BatchDialog.vue'

const { filters, rows, total, loading, page, size, load, search } = useTable(batches.list, { status: '', template_id: '' }, { ordering: '-batch_id' })
const tpls = ref([])
const open = ref(false)
const w = (r, k) => (r.total ? `${(r[k] / r.total) * 100}%` : '0')
onMounted(async () => { load(); tpls.value = await templates.all() })
useRealtimeRefresh(['batch_update'], () => load(true))
</script>
<style scoped>
.clickable :deep(tr) { cursor: pointer; }
.bar { display: flex; height: 8px; border-radius: 4px; background: #e2e8f0; overflow: hidden; }
.bar span { transition: width .3s; }
.ok { background: #22c55e; } .bad { background: #ef4444; } .can { background: #94a3b8; }
.nums { font-size: 12px; margin-top: 4px; }
</style>
