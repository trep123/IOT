<template>
  <div v-if="!fields.length" class="muted">该指令无需参数</div>
  <div v-else class="params">
    <el-form-item v-for="fd in fields" :key="fd.name" :label="fd.name" :required="fd.required" label-width="110px">
      <el-select v-if="fd.enum" v-model="model[fd.name]" :placeholder="`可选：${fd.enum.join(' / ')}`" clearable style="width: 100%">
        <el-option v-for="o in fd.enum" :key="o" :value="o" :label="String(o)" />
      </el-select>
      <el-switch v-else-if="fd.type === 'bool'" v-model="model[fd.name]" />
      <el-input-number v-else-if="fd.type === 'int' || fd.type === 'float'" v-model="model[fd.name]" :min="fd.min ?? -Infinity" :max="fd.max ?? Infinity"
                       :step="fd.type === 'int' ? 1 : 0.1" :precision="fd.type === 'int' ? 0 : undefined" controls-position="right" style="width: 220px" />
      <el-input v-else v-model="model[fd.name]" :placeholder="fd.description || ''" />
      <div class="hint">
        {{ typeLabel[fd.type] || fd.type }}<template v-if="fd.min !== undefined || fd.max !== undefined">，范围 {{ fd.min ?? '-∞' }} ~ {{ fd.max ?? '∞' }}</template>
        <template v-if="fd.default !== undefined">，默认 {{ fd.default }}</template>
      </div>
    </el-form-item>
  </div>
</template>
<script setup>
import { computed, watch } from 'vue'
const props = defineProps({ schema: { type: Object, default: () => ({}) }, model: { type: Object, required: true } })
const typeLabel = { int: '整数', float: '小数', str: '字符串', bool: '布尔' }
const fields = computed(() => Object.entries(props.schema || {}).map(([name, s]) => ({ name, ...s })))
watch(() => props.schema, () => {
  for (const k of Object.keys(props.model)) delete props.model[k]
  for (const fd of fields.value) props.model[fd.name] = fd.default ?? (fd.type === 'bool' ? false : undefined)
}, { immediate: true })

</script>
<style scoped>
.hint { width: 100%; font-size: 12px; color: #94a3b8; line-height: 1.6; }
</style>
