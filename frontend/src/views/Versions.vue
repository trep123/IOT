<template>
  <div class="page">
    <div class="page-head">
      <div><h2>版本与升级包</h2><p>草稿 → 上传并校验全量包 → 发布为可发布 → 用于升级任务；不再使用时废弃</p></div>
      <el-button type="primary" :icon="'Plus'" @click="openVersion()">新建版本</el-button>
    </div>
    <div class="card">
      <div class="toolbar">
        <el-input v-model="filters.search" placeholder="版本号 / 说明" clearable :prefix-icon="'Search'" @keyup.enter="search" @clear="search" />
        <el-select v-model="filters.status" placeholder="状态" clearable @change="search"><el-option v-for="o in options(VERSION)" :key="o.value" v-bind="o" /></el-select>
        <el-input v-model="filters.model" placeholder="适用型号" clearable @keyup.enter="search" @clear="search" />
        <el-button type="primary" @click="search">查询</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" row-key="version_id" @expand-change="onExpand">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="pkgs">
              <div class="card-title">升级包
                <el-button size="small" type="primary" plain :icon="'Upload'" :disabled="row.status === 'DEPRECATED'" @click="openUpload(row)">上传升级包</el-button>
              </div>
              <el-table :data="pkgMap[row.version_id] || []" size="small" v-loading="pkgLoading[row.version_id]">
                <el-table-column prop="package_id" label="ID" width="70" />
                <el-table-column label="类型" width="160"><template #default="{ row: p }"><DictTag :dict="PACKAGE_TYPE" :value="p.package_type" /><span v-if="p.base_version" class="mono muted"> 自 {{ p.base_version }}</span></template></el-table-column>
                <el-table-column prop="file_name" label="文件" min-width="160" show-overflow-tooltip />
                <el-table-column label="大小" width="90"><template #default="{ row: p }">{{ fmtSize(p.size) }}</template></el-table-column>
                <el-table-column label="SHA-256" min-width="200"><template #default="{ row: p }"><el-tooltip :content="p.checksum"><span class="mono">{{ p.checksum?.slice(0, 16) }}…</span></el-tooltip></template></el-table-column>
                <el-table-column label="签名校验" width="100"><template #default="{ row: p }"><el-tag :type="p.verified ? 'success' : 'danger'" size="small">{{ p.verified ? '通过' : '未通过' }}</el-tag></template></el-table-column>
                <el-table-column label="上传时间" width="170"><template #default="{ row: p }">{{ fmtTime(p.created_at) }}</template></el-table-column>
                <el-table-column label="操作" width="180"><template #default="{ row: p }">
                  <el-button link type="primary" @click="verify(row, p)">重新校验</el-button>
                  <el-button link type="primary" @click="pkgApi.download(p)">下载</el-button>
                  <el-popconfirm title="删除该升级包？" @confirm="removePkg(row, p)"><template #reference><el-button link type="danger">删除</el-button></template></el-popconfirm>
                </template></el-table-column>
              </el-table>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="版本号" width="130"><template #default="{ row }"><b class="mono">{{ row.version_no }}</b></template></el-table-column>
        <el-table-column label="状态" width="90"><template #default="{ row }"><DictTag :dict="VERSION" :value="row.status" /></template></el-table-column>
        <el-table-column label="适用型号" min-width="140"><template #default="{ row }">{{ row.applicable_models.join('、') }}</template></el-table-column>
        <el-table-column label="最低可升级" width="110"><template #default="{ row }"><span class="mono">{{ row.min_upgradable_version || '不限' }}</span></template></el-table-column>
        <el-table-column label="升级包" width="150"><template #default="{ row }">
          <span v-if="!row.packages.length" class="muted">未上传</span>
          <template v-else>全量 {{ row.packages.filter((p) => p.package_type === 'FULL').length }} · 差分 {{ row.packages.filter((p) => p.package_type === 'DIFF').length }}
            <el-icon v-if="row.packages.some((p) => p.package_type === 'FULL' && p.verified)" color="#16a34a"><CircleCheckFilled /></el-icon></template>
        </template></el-table-column>
        <el-table-column prop="release_notes" label="更新说明" min-width="200" show-overflow-tooltip />
        <el-table-column label="创建时间" width="170"><template #default="{ row }">{{ fmtTime(row.created_at) }}</template></el-table-column>
        <el-table-column label="操作" width="330" fixed="right"><template #default="{ row }">
          <el-button v-if="row.status === 'DRAFT'" link type="success" @click="publish(row)">发布</el-button>
          <el-button v-if="row.status === 'RELEASABLE'" link type="primary" @click="$router.push({ path: '/tasks', query: { create: row.version_id } })">创建升级任务</el-button>
          <el-button link type="primary" :disabled="row.status === 'DEPRECATED'" @click="openUpload(row)">上传包</el-button>
          <el-button link type="primary" @click="openVersion(row)">编辑</el-button>
          <el-popconfirm v-if="row.status === 'RELEASABLE'" title="废弃后不能再用于新的升级任务，确认？" width="240" @confirm="deprecate(row)"><template #reference><el-button link type="warning">废弃</el-button></template></el-popconfirm>
          <el-popconfirm v-if="row.status === 'DRAFT'" title="删除草稿版本？" @confirm="removeVersion(row)"><template #reference><el-button link type="danger">删除</el-button></template></el-popconfirm>
        </template></el-table-column>
      </el-table>
      <div class="pager"><el-pagination v-model:current-page="page" v-model:page-size="size" :total="total" layout="total, prev, pager, next" @change="load" /></div>
    </div>

    <el-dialog v-model="vDlg" :title="vForm.version_id ? `编辑版本 ${vForm.version_no}` : '新建版本'" width="560px">
      <el-form :model="vForm" label-width="100px">
        <el-form-item label="版本号" required><el-input v-model="vForm.version_no" :disabled="vForm.version_id && vForm.status !== 'DRAFT'" placeholder="如 1.2.0" /></el-form-item>
        <el-form-item label="适用型号" required>
          <el-select v-model="vForm.applicable_models" multiple filterable allow-create default-first-option placeholder="选择或输入型号" style="width: 100%">
            <el-option v-for="m in models" :key="m" :value="m" :label="m" />
          </el-select>
        </el-form-item>
        <el-form-item label="最低可升级"><el-input v-model="vForm.min_upgradable_version" placeholder="低于该版本的设备不能直接升级，留空不限" /></el-form-item>
        <el-form-item label="更新说明"><el-input v-model="vForm.release_notes" type="textarea" :rows="4" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="vDlg = false">取消</el-button><el-button type="primary" @click="saveVersion">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="uDlg" :title="`上传升级包 · ${uVersion?.version_no}`" width="560px" @closed="uFile = null">
      <el-form label-width="100px">
        <el-form-item label="包类型">
          <el-radio-group v-model="uForm.package_type"><el-radio value="FULL">全量包</el-radio><el-radio value="DIFF">差分包</el-radio></el-radio-group>
        </el-form-item>
        <el-form-item v-if="uForm.package_type === 'DIFF'" label="起始版本" required>
          <el-select v-model="uForm.base_version" filterable allow-create placeholder="差分包适用的设备当前版本" style="width: 100%">
            <el-option v-for="v in deviceVersions" :key="v" :value="v" :label="v" />
          </el-select>
        </el-form-item>
        <el-form-item label="文件" required>
          <el-upload drag :auto-upload="false" :limit="1" :on-change="(f) => (uFile = f.raw)" :on-remove="() => (uFile = null)" style="width: 100%">
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖拽文件到这里，或 <em>点击选择</em></div>
          </el-upload>
        </el-form-item>
        <el-form-item label="SHA-256">
          <el-input v-model="uForm.checksum" placeholder="可选：填写后平台会比对，不一致将拒绝" />
          <el-button link type="primary" :disabled="!uFile" :loading="hashing" @click="calcHash">在浏览器中计算</el-button>
        </el-form-item>
        <el-progress v-if="uploading" :percentage="uProgress" />
      </el-form>
      <template #footer><el-button @click="uDlg = false">取消</el-button><el-button type="primary" :loading="uploading" :disabled="!uFile" @click="upload">上传</el-button></template>
    </el-dialog>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { devices, packages as pkgApi, versions } from '@/api'
import { PACKAGE_TYPE, VERSION, options } from '@/utils/dict'
import { fmtSize, fmtTime } from '@/utils/format'
import { useTable } from '@/utils/useTable'
import DictTag from '@/components/DictTag.vue'

const { filters, rows, total, loading, page, size, load, search } = useTable(versions.list, { search: '', status: '', model: '' }, { ordering: '-version_id' })
const models = ref([])
const deviceVersions = ref([])
const pkgMap = reactive({})
const pkgLoading = reactive({})

async function loadPkgs(v) {
  pkgLoading[v.version_id] = true
  try { pkgMap[v.version_id] = (await pkgApi.list({ version_id: v.version_id, page_size: 100 })).results } finally { pkgLoading[v.version_id] = false }
}
function onExpand(row, expanded) { if (expanded.some((r) => r.version_id === row.version_id)) loadPkgs(row) }

const vDlg = ref(false)
const vForm = reactive({})
function openVersion(row) {
  Object.assign(vForm, row ? { ...row, applicable_models: [...row.applicable_models] } : { version_id: null, version_no: '', applicable_models: [], min_upgradable_version: '', release_notes: '', status: 'DRAFT' })
  vDlg.value = true
}
async function saveVersion() {
  const data = { version_no: vForm.version_no, applicable_models: vForm.applicable_models, min_upgradable_version: vForm.min_upgradable_version, release_notes: vForm.release_notes }
  if (vForm.version_id) await versions.update(vForm.version_id, data); else await versions.create(data)
  ElMessage.success('已保存'); vDlg.value = false; load()
}
async function publish(row) {
  await ElMessageBox.confirm(`发布版本 ${row.version_no}？发布后可用于创建升级任务，版本号不可再改。`, '发布版本', { type: 'info' })
  await versions.publish(row.version_id); ElMessage.success('已发布'); load()
}
async function deprecate(row) { await versions.deprecate(row.version_id); ElMessage.success('已废弃'); load() }
async function removeVersion(row) { await versions.remove(row.version_id); ElMessage.success('已删除'); load() }

const uDlg = ref(false)
const uVersion = ref(null)
const uForm = reactive({ package_type: 'FULL', base_version: '', checksum: '' })
const uFile = ref(null)
const uploading = ref(false)
const uProgress = ref(0)
const hashing = ref(false)
function openUpload(row) { uVersion.value = row; Object.assign(uForm, { package_type: 'FULL', base_version: '', checksum: '' }); uDlg.value = true }
async function calcHash() {
  hashing.value = true
  try {
    const buf = await uFile.value.arrayBuffer()
    const h = await crypto.subtle.digest('SHA-256', buf)
    uForm.checksum = [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, '0')).join('')
  } catch { ElMessage.warning('当前环境不支持浏览器内计算（需 HTTPS 或 localhost）') } finally { hashing.value = false }
}
async function upload() {
  if (uForm.package_type === 'DIFF' && !uForm.base_version) return ElMessage.warning('差分包需要填写起始版本')
  const fd = new FormData()
  fd.append('version_id', uVersion.value.version_id)
  fd.append('package_type', uForm.package_type)
  if (uForm.package_type === 'DIFF') fd.append('base_version', uForm.base_version)
  if (uForm.checksum) fd.append('checksum', uForm.checksum)
  fd.append('file', uFile.value)
  uploading.value = true; uProgress.value = 0
  try {
    const p = await pkgApi.upload(fd, (v) => (uProgress.value = v))
    ElMessage.success(`上传成功，签名校验${p.verified ? '通过' : '未通过'}`)
    uDlg.value = false
    await load(); loadPkgs(uVersion.value)
  } finally { uploading.value = false }
}
async function verify(v, p) { const r = await pkgApi.verify(p.package_id); ElMessage[r.verified ? 'success' : 'error'](r.verified ? '校验通过' : '校验未通过'); loadPkgs(v); load() }
async function removePkg(v, p) { await pkgApi.remove(p.package_id); ElMessage.success('已删除'); loadPkgs(v); load() }

onMounted(async () => {
  load()
  const s = await devices.summary()
  models.value = s.by_model.map((m) => m.model)
  deviceVersions.value = s.by_version.map((v) => v.current_version).filter(Boolean)
})
</script>
<style scoped>
.pkgs { padding: 4px 48px 12px; }
</style>
