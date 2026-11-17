<template>
  <div class="page">
    <div class="page-head">
      <div><h2>指令模板</h2><p>定义可下发的指令、参数校验规则、超时时间与是否关键操作</p></div>
      <el-button type="primary" :icon="'Plus'" @click="open()">新建模板</el-button>
    </div>
    <div class="card">
      <div class="toolbar"><el-input v-model="filters.search" placeholder="编码 / 名称" clearable :prefix-icon="'Search'" @keyup.enter="search" @clear="search" /><el-button type="primary" @click="search">查询</el-button></div>
      <el-table v-loading="loading" :data="rows">
        <el-table-column label="编码" min-width="140"><template #default="{ row }"><span class="mono">{{ row.code }}</span></template></el-table-column>
        <el-table-column prop="name" label="名称" min-width="130" />
        <el-table-column label="类型" width="150"><template #default="{ row }">
          <el-tag v-if="row.is_critical" type="danger" size="small">关键操作</el-tag>
          <el-tag v-if="row.is_system" type="info" size="small" style="margin-left: 4px">系统内置</el-tag>
          <span v-if="!row.is_critical && !row.is_system" class="muted">普通</span></template></el-table-column>
        <el-table-column label="适用型号" min-width="140"><template #default="{ row }">{{ !row.applicable_models?.length || row.applicable_models.includes('*') ? '全部型号' : row.applicable_models.join('、') }}</template></el-table-column>
        <el-table-column label="参数" min-width="220"><template #default="{ row }">
          <span v-if="!Object.keys(row.param_schema || {}).length" class="muted">无</span>
          <el-tag v-for="(s, k) in row.param_schema" :key="k" size="small" effect="plain" class="ptag">{{ k }}: {{ s.type }}{{ s.required ? '*' : '' }}</el-tag></template></el-table-column>
        <el-table-column label="超时" width="80"><template #default="{ row }">{{ row.timeout_seconds }}s</template></el-table-column>
        <el-table-column prop="description" label="说明" min-width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="130"><template #default="{ row }">
          <template v-if="!row.is_system">
            <el-button link type="primary" @click="open(row)">编辑</el-button>
            <el-popconfirm title="删除该模板？" @confirm="remove(row)"><template #reference><el-button link type="danger">删除</el-button></template></el-popconfirm>
          </template><span v-else class="muted">不可修改</span></template></el-table-column>
      </el-table>
      <div class="pager"><el-pagination v-model:current-page="page" :total="total" layout="total, prev, pager, next" @change="load" /></div>
    </div>

    <el-dialog v-model="dlg" :title="form.template_id ? '编辑指令模板' : '新建指令模板'" width="760px">
      <el-form :model="form" label-width="100px">
        <div class="grid grid-2" style="gap: 0 16px">
          <el-form-item label="编码" required><el-input v-model="form.code" placeholder="如 REBOOT" /></el-form-item>
          <el-form-item label="名称" required><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="超时（秒）"><el-input-number v-model="form.timeout_seconds" :min="1" controls-position="right" /></el-form-item>
          <el-form-item label="关键操作"><el-switch v-model="form.is_critical" /><span class="muted" style="margin-left: 8px">需二次确认并审计</span></el-form-item>
        </div>
        <el-form-item label="适用型号">
          <el-select v-model="form.applicable_models" multiple filterable allow-create default-first-option placeholder="留空或 * 表示全部型号" style="width: 100%">
            <el-option value="*" label="全部型号 (*)" /><el-option v-for="m in models" :key="m" :value="m" :label="m" />
          </el-select>
        </el-form-item>
        <el-form-item label="参数定义">
          <el-table :data="params" size="small" class="ptable">
            <el-table-column label="参数名" min-width="110"><template #default="{ row }"><el-input v-model="row.name" size="small" /></template></el-table-column>
            <el-table-column label="类型" width="100"><template #default="{ row }"><el-select v-model="row.type" size="small"><el-option v-for="t in ['int', 'float', 'str', 'bool']" :key="t" :value="t" /></el-select></template></el-table-column>
            <el-table-column label="必填" width="55"><template #default="{ row }"><el-checkbox v-model="row.required" /></template></el-table-column>
            <el-table-column label="最小" width="80"><template #default="{ row }"><el-input v-model="row.min" size="small" :disabled="!numeric(row)" /></template></el-table-column>
            <el-table-column label="最大" width="80"><template #default="{ row }"><el-input v-model="row.max" size="small" :disabled="!numeric(row)" /></template></el-table-column>
            <el-table-column label="可选值（逗号分隔）" min-width="130"><template #default="{ row }"><el-input v-model="row.enum" size="small" :disabled="row.type === 'bool'" /></template></el-table-column>
            <el-table-column label="默认" width="80"><template #default="{ row }"><el-input v-model="row.default" size="small" /></template></el-table-column>
            <el-table-column width="44"><template #default="{ $index }"><el-button link type="danger" :icon="'Delete'" @click="params.splice($index, 1)" /></template></el-table-column>
          </el-table>
          <el-button size="small" :icon="'Plus'" style="margin-top: 8px" @click="params.push({ name: '', type: 'int', required: false, min: '', max: '', enum: '', default: '' })">添加参数</el-button>
        </el-form-item>
        <el-form-item label="说明"><el-input v-model="form.description" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dlg = false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template>
    </el-dialog>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { devices, templates } from '@/api'
import { useTable } from '@/utils/useTable'

const { filters, rows, total, loading, page, load, search } = useTable(templates.list, { search: '' })
const models = ref([])
const dlg = ref(false)
const form = reactive({})
const params = ref([])
const numeric = (r) => r.type === 'int' || r.type === 'float'

function open(row) {
  Object.assign(form, row ? { ...row, applicable_models: [...(row.applicable_models || [])] }
    : { template_id: null, code: '', name: '', applicable_models: ['*'], is_critical: false, timeout_seconds: 30, description: '' })
  params.value = Object.entries(row?.param_schema || {}).map(([name, s]) => ({
    name, type: s.type, required: !!s.required, min: s.min ?? '', max: s.max ?? '', enum: (s.enum || []).join(','), default: s.default ?? '',
  }))
  dlg.value = true
}
function conv(type, v) {
  if (v === '' || v === null || v === undefined) return undefined
  if (type === 'int') return parseInt(v, 10)
  if (type === 'float') return parseFloat(v)
  if (type === 'bool') return v === true || v === 'true' || v === '1'
  return String(v)
}
function buildSchema() {
  const schema = {}
  for (const p of params.value) {
    if (!p.name) continue
    const s = { type: p.type, required: p.required }
    if (numeric(p)) { if (conv(p.type, p.min) !== undefined) s.min = conv(p.type, p.min); if (conv(p.type, p.max) !== undefined) s.max = conv(p.type, p.max) }
    if (p.enum && p.type !== 'bool') s.enum = String(p.enum).split(',').map((x) => conv(p.type, x.trim())).filter((x) => x !== undefined)
    if (conv(p.type, p.default) !== undefined) s.default = conv(p.type, p.default)
    schema[p.name] = s
  }
  return schema
}
async function save() {
  if (!form.code || !form.name) return ElMessage.warning('请填写编码和名称')
  const data = { code: form.code, name: form.name, applicable_models: form.applicable_models?.length ? form.applicable_models : ['*'],
    is_critical: form.is_critical, timeout_seconds: form.timeout_seconds, description: form.description, param_schema: buildSchema() }
  if (form.template_id) await templates.update(form.template_id, data); else await templates.create(data)
  ElMessage.success('已保存'); dlg.value = false; load()
}
async function remove(row) { await templates.remove(row.template_id); ElMessage.success('已删除'); load() }
onMounted(async () => { load(); models.value = (await devices.summary()).by_model.map((m) => m.model) })
</script>
<style scoped>
.ptag { margin: 2px 4px 2px 0; }
.ptable { width: 100%; }
</style>
