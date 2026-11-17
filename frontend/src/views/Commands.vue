<template>
  <div class="page">
    <div class="page-head">
      <div><h2>指令记录</h2><p>每条指令的完整生命周期：待发送 → 已发送 → 已送达 → 成功 / 失败 / 超时</p></div>
      <el-button type="primary" :icon="'Promotion'" @click="open = true">下发指令</el-button>
    </div>
    <div class="card">
      <div class="toolbar">
        <el-input v-model="filters.device_id" placeholder="设备编号" clearable @keyup.enter="search" @clear="search" />
        <el-select v-model="filters.template_code" placeholder="指令" clearable filterable @change="search">
          <el-option v-for="t in tpls" :key="t.code" :value="t.code" :label="`${t.name}（${t.code}）`" />
        </el-select>
        <el-select v-model="filters.status__in" placeholder="状态" clearable multiple collapse-tags style="width: 220px" @change="search">
          <el-option v-for="o in options(COMMAND)" :key="o.value" v-bind="o" />
        </el-select>
        <el-select v-model="filters.is_critical" placeholder="关键操作" clearable @change="search">
          <el-option :value="true" label="仅关键操作" /><el-option :value="false" label="非关键操作" />
        </el-select>
        <el-input v-model="filters.batch_id" placeholder="批次 ID" clearable style="width: 120px" @keyup.enter="search" @clear="search" />
        <el-date-picker v-model="rangeV" type="datetimerange" start-placeholder="创建时间起" end-placeholder="止" style="width: 340px" @change="search" />
        <el-button type="primary" @click="search">查询</el-button>
        <el-button @click="rangeV = null; reset()">重置</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" @sort-change="onSort">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="expand">
              <el-descriptions :column="4" size="small" border>
                <el-descriptions-item label="创建">{{ fmtTime(row.created_at) }}</el-descriptions-item>
                <el-descriptions-item label="发送">{{ fmtTime(row.sent_at) }}</el-descriptions-item>
                <el-descriptions-item label="送达">{{ fmtTime(row.delivered_at) }}</el-descriptions-item>
                <el-descriptions-item label="完成">{{ fmtTime(row.finished_at) }}</el-descriptions-item>
              </el-descriptions>
              <div class="cols">
                <div><div class="lbl">参数</div><pre class="json">{{ JSON.stringify(row.params, null, 2) }}</pre></div>
                <div><div class="lbl">结果（结果码 {{ row.result_code ?? '—' }}）</div><pre class="json">{{ row.result_data ? JSON.stringify(row.result_data, null, 2) : row.error_msg || '—' }}</pre></div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="command_id" label="ID" width="80" sortable="custom" />
        <el-table-column label="设备" min-width="130"><template #default="{ row }"><span class="link mono" @click="$router.push(`/devices/${row.device_id}`)">{{ row.device_id }}</span></template></el-table-column>
        <el-table-column label="指令" min-width="180"><template #default="{ row }">{{ row.template_name }} <span class="muted mono">{{ row.template_code }}</span> <el-tag v-if="row.is_critical" type="danger" size="small">关键</el-tag></template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><DictTag :dict="COMMAND" :value="row.status" /></template></el-table-column>
        <el-table-column label="结果 / 错误" min-width="180" show-overflow-tooltip><template #default="{ row }"><span :class="{ err: row.error_msg }">{{ row.error_msg || (row.result_data ? JSON.stringify(row.result_data) : '—') }}</span></template></el-table-column>
        <el-table-column label="来源" width="90"><template #default="{ row }"><span v-if="row.batch_id" class="link" @click="$router.push(`/batches/${row.batch_id}`)">批次 #{{ row.batch_id }}</span><span v-else class="muted">单发</span></template></el-table-column>
        <el-table-column prop="operator_id" label="操作人" width="90" />
        <el-table-column prop="created_at" label="创建时间" width="170" sortable="custom"><template #default="{ row }">{{ fmtTime(row.created_at) }}</template></el-table-column>
      </el-table>
      <div class="pager"><el-pagination v-model:current-page="page" v-model:page-size="size" :total="total" :page-sizes="[20, 50, 100]" layout="total, sizes, prev, pager, next, jumper" @change="load" /></div>
    </div>
    <CommandDialog v-model="open" @sent="search" />
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { commands, templates } from '@/api'
import { COMMAND, options } from '@/utils/dict'
import { fmtTime } from '@/utils/format'
import { useTable } from '@/utils/useTable'
import { useRealtimeRefresh } from '@/utils/useRealtimeRefresh'
import DictTag from '@/components/DictTag.vue'
import CommandDialog from '@/components/CommandDialog.vue'

const rangeV = ref(null)
const range = () => (rangeV.value ? { created_after: rangeV.value[0].toISOString(), created_before: rangeV.value[1].toISOString() } : {})
const { filters, rows, total, loading, page, size, load, search, reset, onSort } = useTable((q) => commands.list({ ...q, ...range() }),
  { device_id: '', template_code: '', status__in: [], is_critical: '', batch_id: '' }, { ordering: '-command_id' })
const tpls = ref([])
const open = ref(false)
onMounted(async () => { load(); tpls.value = await templates.all() })
useRealtimeRefresh(['command_update'], () => load(true), { wait: 1000 })
</script>
<style scoped>
.expand { padding: 4px 48px 8px; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 10px; }
.lbl { font-size: 12px; color: #64748b; margin-bottom: 4px; }
.err { color: #dc2626; }
</style>
