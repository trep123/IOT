<template>
  <div class="page">
    <div class="page-head">
      <div><h2>设备分组</h2><p>分组可作为批量控制与升级任务的目标范围</p></div>
      <el-button type="primary" :icon="'Plus'" @click="open()">新建分组</el-button>
    </div>
    <div class="card">
      <div class="toolbar"><el-input v-model="filters.search" placeholder="分组名称" clearable :prefix-icon="'Search'" @keyup.enter="search" @clear="search" /><el-button type="primary" @click="search">查询</el-button></div>
      <el-table v-loading="loading" :data="rows">
        <el-table-column prop="group_id" label="ID" width="80" />
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column prop="description" label="说明" min-width="220" show-overflow-tooltip />
        <el-table-column label="设备数" width="100"><template #default="{ row }"><span class="link" @click="$router.push({ path: '/devices', query: { group_id: row.group_id } })">{{ row.device_count ?? 0 }}</span></template></el-table-column>
        <el-table-column label="创建时间" width="180"><template #default="{ row }">{{ fmtTime(row.created_at) }}</template></el-table-column>
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button link type="primary" @click="open(row)">编辑</el-button>
            <el-popconfirm title="删除分组？组内设备将变为未分组" @confirm="remove(row)"><template #reference><el-button link type="danger">删除</el-button></template></el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager"><el-pagination v-model:current-page="page" v-model:page-size="size" :total="total" layout="total, prev, pager, next" @change="load" /></div>
    </div>
    <el-dialog v-model="dlg" :title="form.group_id ? '编辑分组' : '新建分组'" width="460px">
      <el-form :model="form" label-width="70px">
        <el-form-item label="名称" required><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="说明"><el-input v-model="form.description" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dlg = false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template>
    </el-dialog>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { groups } from '@/api'
import { fmtTime } from '@/utils/format'
import { useTable } from '@/utils/useTable'

const { filters, rows, total, loading, page, size, load, search } = useTable(groups.list, { search: '' })
const dlg = ref(false)
const form = reactive({ group_id: null, name: '', description: '' })
function open(row) { Object.assign(form, row ? { group_id: row.group_id, name: row.name, description: row.description } : { group_id: null, name: '', description: '' }); dlg.value = true }
async function save() {
  if (!form.name) return ElMessage.warning('请填写名称')
  if (form.group_id) await groups.update(form.group_id, { name: form.name, description: form.description })
  else await groups.create({ name: form.name, description: form.description })
  ElMessage.success('已保存'); dlg.value = false; load()
}
async function remove(row) { await groups.remove(row.group_id); ElMessage.success('已删除'); load() }
onMounted(load)
</script>
