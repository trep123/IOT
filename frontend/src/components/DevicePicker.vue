<template>
  <el-select :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)" :multiple="multiple"
             filterable remote :remote-method="search" :loading="loading" clearable collapse-tags collapse-tags-tooltip
             :max-collapse-tags="4" :placeholder="placeholder" style="width: 100%" @visible-change="(v) => v && !opts.length && search('')">
    <el-option v-for="d in opts" :key="d.device_id" :value="d.device_id" :label="`${d.device_id}（${d.name}）`">
      <div class="opt">
        <span><span class="mono">{{ d.device_id }}</span> <span class="muted">{{ d.name }}</span></span>
        <span class="right"><span class="muted">{{ d.model }} · {{ d.current_version || '—' }}</span>
          <DictTag :dict="ONLINE" :value="d.online_status" /></span>
      </div>
    </el-option>
  </el-select>
</template>
<script setup>
import { ref } from 'vue'
import { devices } from '@/api'
import { ONLINE } from '@/utils/dict'
import DictTag from './DictTag.vue'

const props = defineProps({ modelValue: [Array, String], multiple: Boolean, placeholder: { type: String, default: '搜索设备编号或名称' }, filters: Object })
defineEmits(['update:modelValue'])
const opts = ref([])
const loading = ref(false)
async function search(q) {
  loading.value = true
  try { opts.value = (await devices.list({ search: q, page_size: 50, ...(props.filters || {}) })).results } finally { loading.value = false }
}
</script>
<style scoped>
.opt { display: flex; justify-content: space-between; gap: 12px; width: 100%; }
.right { display: flex; gap: 8px; align-items: center; }
</style>
