<template>
  <el-tag :type="item.type || undefined" :size="size" effect="light" disable-transitions>
    <span v-if="dot" class="dot" :class="item.type" />{{ item.label }}
  </el-tag>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps({ dict: Object, value: String, size: { type: String, default: 'small' }, dot: Boolean })
const item = computed(() => props.dict?.[props.value] || { label: props.value || '—', type: 'info' })
</script>
<style scoped>
.dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 5px; background: currentColor; vertical-align: middle; }
.dot.success { animation: pulse 2s infinite; }
@keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(34,197,94,.5) } 70% { box-shadow: 0 0 0 5px rgba(34,197,94,0) } 100% { box-shadow: 0 0 0 0 rgba(34,197,94,0) } }
</style>
