<template>
  <div class="code-block">
    <div class="bar">
      <span class="title">{{ title }}</span>
      <span class="lang" v-if="lang">{{ lang }}</span>
      <div class="grow" />
      <span class="lines" v-if="lines > 1">{{ lines }} 行</span>
      <el-button v-if="filename" link :icon="'Download'" @click="download">下载</el-button>
      <el-button link :icon="'CopyDocument'" @click="copyText(code)">复制</el-button>
    </div>
    <pre :style="{ maxHeight }"><code>{{ code }}</code></pre>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { copyText } from '@/utils/clipboard'

const props = defineProps({
  code: { type: String, default: '' },
  title: { type: String, default: '' },
  lang: { type: String, default: '' },
  filename: { type: String, default: '' },
  maxHeight: { type: String, default: '520px' },
})
const lines = computed(() => props.code.trimEnd().split('\n').length)

function download() {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([props.code], { type: 'text/plain;charset=utf-8' }))
  a.download = props.filename
  a.click()
  URL.revokeObjectURL(a.href)
}
</script>

<style scoped>
.code-block { border: 1px solid #1e293b; border-radius: 10px; overflow: hidden; background: #0f172a; margin: 10px 0; }
.bar { display: flex; align-items: center; gap: 10px; padding: 6px 12px; background: #1e293b; color: #cbd5e1; font-size: 12.5px; }
.bar .el-button { color: #93c5fd; }
.title { font-weight: 600; color: #e2e8f0; }
.lang { padding: 1px 8px; border-radius: 10px; background: #334155; font-size: 11.5px; }
.lines { color: #64748b; }
.grow { flex: 1; }
pre { margin: 0; padding: 14px 16px; overflow: auto; color: #e2e8f0; font: 12.5px/1.65 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; tab-size: 2; }
</style>
