<template>
  <div class="up">
    <div class="steps">
      <span v-for="(s, i) in STAGE_ORDER.slice(1)" :key="s" class="s" :class="cls(i + 1)"><el-tooltip :content="STAGE[s].label"><i /></el-tooltip></span>
    </div>
    <DictTag :dict="STAGE" :value="record.stage" />
    <span v-if="running" class="muted pct">{{ record.progress }}%</span>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { STAGE, STAGE_ORDER } from '@/utils/dict'
import DictTag from './DictTag.vue'
const props = defineProps({ record: Object })
const idx = computed(() => STAGE_ORDER.indexOf(props.record.stage))
const running = computed(() => ['DOWNLOADING', 'VERIFYING', 'INSTALLING', 'REBOOTING'].includes(props.record.stage))
function cls(i) {
  if (props.record.stage === 'FAILED') return 'fail'
  if (i < idx.value || props.record.stage === 'SUCCESS') return 'done'
  if (i === idx.value) return 'cur'
  return ''
}
</script>
<style scoped>
.up { display: flex; align-items: center; gap: 10px; }
.steps { display: flex; gap: 3px; }
.s i { display: block; width: 18px; height: 6px; border-radius: 3px; background: #e2e8f0; }
.s.done i { background: #22c55e; }
.s.cur i { background: #3b82f6; animation: blink 1.2s infinite; }
.s.fail i { background: #fca5a5; }
.pct { font-size: 12px; font-variant-numeric: tabular-nums; }
@keyframes blink { 50% { opacity: .4 } }
</style>
