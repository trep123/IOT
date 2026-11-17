<template>
  <div class="stat card" :class="color">
    <div class="icon"><el-icon><component :is="icon" /></el-icon></div>
    <div class="body">
      <div class="label">{{ label }}</div>
      <div class="value">{{ value }}<span v-if="unit" class="unit">{{ unit }}</span></div>
      <div v-if="hint" class="hint">{{ hint }}</div>
    </div>
  </div>
</template>
<script setup>
defineProps({ label: String, value: [String, Number], unit: String, hint: String, icon: { type: String, default: 'DataLine' }, color: { type: String, default: 'blue' } })
</script>
<style scoped>
.stat { display: flex; gap: 16px; align-items: center; }
.icon { width: 48px; height: 48px; border-radius: 12px; display: grid; place-items: center; font-size: 22px; flex: none; }
.blue .icon { background: #eff6ff; color: #2563eb; }
.green .icon { background: #f0fdf4; color: #16a34a; }
.gray .icon { background: #f1f5f9; color: #64748b; }
.orange .icon { background: #fff7ed; color: #ea580c; }
.purple .icon { background: #f5f3ff; color: #7c3aed; }
.red .icon { background: #fef2f2; color: #dc2626; }
.label { color: #64748b; font-size: 13px; }
.value { font-size: 26px; font-weight: 700; margin-top: 2px; font-variant-numeric: tabular-nums; }
.unit { font-size: 13px; font-weight: 400; color: #94a3b8; margin-left: 4px; }
.hint { color: #94a3b8; font-size: 12px; margin-top: 2px; }
</style>
