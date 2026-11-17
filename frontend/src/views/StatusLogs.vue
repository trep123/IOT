<template>
  <div class="page">
    <div class="page-head">
      <div><h2>状态变更记录</h2><p>每次上线 / 离线的原因与上一状态的持续时长</p></div>
      <el-button :icon="'Download'" @click="statusLogs.export(query())">导出 CSV</el-button>
    </div>
    <div class="card">
      <div class="toolbar">
        <el-input v-model="filters.device_id" placeholder="设备编号" clearable @keyup.enter="search" @clear="search" />
        <el-select v-model="filters.to_status" placeholder="变更为" clearable @change="search"><el-option v-for="o in options(ONLINE)" :key="o.value" v-bind="o" /></el-select>
        <el-select v-model="filters.reason" placeholder="原因" clearable @change="search"><el-option v-for="o in options(STATUS_REASON)" :key="o.value" v-bind="o" /></el-select>
        <el-date-picker v-model="rangeV" type="datetimerange" start-placeholder="开始时间" end-placeholder="结束时间" style="width: 340px" @change="search" />
        <el-button type="primary" @click="search">查询</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" @sort-change="onSort">
        <el-table-column prop="log_id" label="ID" width="80" />
        <el-table-column label="设备" min-width="140"><template #default="{ row }"><span class="link mono" @click="$router.push(`/devices/${row.device_id}`)">{{ row.device_id }}</span></template></el-table-column>
        <el-table-column label="状态变化" width="190"><template #default="{ row }"><DictTag :dict="ONLINE" :value="row.from_status" /> <el-icon class="arrow"><Right /></el-icon> <DictTag :dict="ONLINE" :value="row.to_status" /></template></el-table-column>
        <el-table-column label="原因" width="130"><template #default="{ row }"><DictTag :dict="STATUS_REASON" :value="row.reason" /></template></el-table-column>
        <el-table-column label="上一状态持续" width="140"><template #default="{ row }">{{ fmtDuration(row.duration_seconds) }}</template></el-table-column>
        <el-table-column prop="occurred_at" label="发生时间" width="180" sortable="custom"><template #default="{ row }">{{ fmtTime(row.occurred_at) }}</template></el-table-column>
      </el-table>
      <div class="pager"><el-pagination v-model:current-page="page" v-model:page-size="size" :total="total" :page-sizes="[20, 50, 100]" layout="total, sizes, prev, pager, next" @change="load" /></div>
    </div>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { statusLogs } from '@/api'
import { ONLINE, STATUS_REASON, options } from '@/utils/dict'
import { fmtTime, fmtDuration } from '@/utils/format'
import { useTable } from '@/utils/useTable'
import { useRealtimeRefresh } from '@/utils/useRealtimeRefresh'
import DictTag from '@/components/DictTag.vue'

const rangeV = ref(null)
const range = () => (rangeV.value ? { occurred_after: rangeV.value[0].toISOString(), occurred_before: rangeV.value[1].toISOString() } : {})
const { filters, rows, total, loading, page, size, load, search, onSort } = useTable((q) => statusLogs.list({ ...q, ...range() }),
  { device_id: '', to_status: '', reason: '' }, { ordering: '-occurred_at' })
const query = () => ({ ...filters, ...range() })
onMounted(load)
useRealtimeRefresh(['device_status'], () => page.value === 1 && load(true))
</script>
<style scoped>.arrow { vertical-align: middle; color: #94a3b8; margin: 0 2px; }</style>
