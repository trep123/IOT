<template><div ref="el" :style="{ height }" /></template>
<script setup>
import { onMounted, onBeforeUnmount, ref, watch, shallowRef } from 'vue'
import * as echarts from 'echarts/core'
import { PieChart, BarChart, LineChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent, GridComponent, TitleComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([PieChart, BarChart, LineChart, TooltipComponent, LegendComponent, GridComponent, TitleComponent, CanvasRenderer])

const props = defineProps({ option: Object, height: { type: String, default: '260px' } })
const el = ref()
const chart = shallowRef()
const resize = () => chart.value?.resize()
onMounted(() => {
  chart.value = echarts.init(el.value)
  chart.value.setOption(props.option || {})
  window.addEventListener('resize', resize)
})
watch(() => props.option, (o) => chart.value?.setOption(o || {}, true), { deep: true })
onBeforeUnmount(() => { window.removeEventListener('resize', resize); chart.value?.dispose() })
</script>
