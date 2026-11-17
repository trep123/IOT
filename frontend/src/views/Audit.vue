<template>
  <div class="page">
    <div class="page-head">
      <div><h2>操作审计</h2><p>关键指令、批量控制、版本发布与回滚等操作的统一记录</p></div>
      <el-button :icon="'Download'" @click="audit.export(query())">导出 CSV</el-button>
    </div>
    <div class="card">
      <div class="toolbar">
        <el-select v-model="filters.op_type" placeholder="操作类型" clearable filterable @change="search"><el-option v-for="o in options(OP_TYPE)" :key="o.value" v-bind="o" /></el-select>
        <el-select v-model="filters.target_type" placeholder="对象类型" clearable @change="search"><el-option v-for="o in options(TARGET_TYPE)" :key="o.value" v-bind="o" /></el-select>
        <el-input v-model="filters.target_id" placeholder="对象 ID" clearable @keyup.enter="search" @clear="search" />
        <el-input v-model="filters.operator_id" placeholder="操作人" clearable @keyup.enter="search" @clear="search" />
        <el-select v-model="filters.result" placeholder="结果" clearable @change="search"><el-option v-for="(v, k) in RESULT" :key="k" :value="k" :label="v.label" /></el-select>
        <el-date-picker v-model="rangeV" type="datetimerange" start-placeholder="开始时间" end-placeholder="结束时间" style="width: 340px" @change="search" />
        <el-button type="primary" @click="search">查询</el-button>
        <el-button @click="rangeV = null; reset()">重置</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" @sort-change="onSort">
        <el-table-column type="expand"><template #default="{ row }"><div style="padding: 4px 48px"><pre class="json">{{ JSON.stringify(row.detail, null, 2) }}</pre></div></template></el-table-column>
        <el-table-column prop="op_id" label="ID" width="80" />
        <el-table-column prop="op_time" label="时间" width="180" sortable="custom"><template #default="{ row }">{{ fmtTime(row.op_time) }}</template></el-table-column>
        <el-table-column prop="operator_id" label="操作人" width="100" />
        <el-table-column label="操作类型" width="190"><template #default="{ row }"><DictTag :dict="OP_TYPE" :value="row.op_type" /></template></el-table-column>
        <el-table-column label="对象" width="150"><template #default="{ row }">{{ TARGET_TYPE[row.target_type]?.label || row.target_type }} <span class="link mono" @click="goto(row)">{{ row.target_id }}</span></template></el-table-column>
        <el-table-column label="结果" width="90"><template #default="{ row }"><DictTag :dict="RESULT" :value="row.result" /></template></el-table-column>
        <el-table-column label="详情" min-width="260" show-overflow-tooltip><template #default="{ row }"><span class="mono muted">{{ JSON.stringify(row.detail) }}</span></template></el-table-column>
      </el-table>
      <div class="pager"><el-pagination v-model:current-page="page" v-model:page-size="size" :total="total" :page-sizes="[20, 50, 100]" layout="total, sizes, prev, pager, next, jumper" @change="load" /></div>
    </div>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { audit } from '@/api'
import { OP_TYPE, TARGET_TYPE, options } from '@/utils/dict'
import { fmtTime } from '@/utils/format'
import { useTable } from '@/utils/useTable'
import DictTag from '@/components/DictTag.vue'

const router = useRouter()
const RESULT = { SUCCESS: { label: '成功', type: 'success' }, FAILED: { label: '失败', type: 'danger' }, TIMEOUT: { label: '超时', type: 'warning' }, PAUSED: { label: '已暂停', type: 'warning' } }
const rangeV = ref(null)
const range = () => (rangeV.value ? { op_time_after: rangeV.value[0].toISOString(), op_time_before: rangeV.value[1].toISOString() } : {})
const { filters, rows, total, loading, page, size, load, search, reset, onSort } = useTable((q) => audit.list({ ...q, ...range() }),
  { op_type: '', target_type: '', target_id: '', operator_id: '', result: '' }, { ordering: '-op_time' })
const query = () => ({ ...filters, ...range() })
function goto(r) {
  const map = { DEVICE: `/devices/${r.target_id}`, BATCH: `/batches/${r.target_id}`, TASK: `/tasks/${r.target_id}`, VERSION: '/versions', PACKAGE: '/versions' }
  if (r.target_type === 'COMMAND') return router.push({ path: '/commands' })
  if (map[r.target_type]) router.push(map[r.target_type])
}
onMounted(load)
</script>
