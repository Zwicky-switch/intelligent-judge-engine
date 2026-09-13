<template>
  <div ref="el" :style="{ height, width }"></div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref, watch, nextTick } from 'vue'
// ECharts 按需引入: 仅注册项目实际使用的图表类型与组件,
// 相比 import * as echarts 全量引入可减少约 60% 打包体积。
import * as echarts from 'echarts/core'
import { BarChart, RadarChart, HeatmapChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent,
  RadarComponent, VisualMapComponent, TitleComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  BarChart, RadarChart, HeatmapChart,
  GridComponent, TooltipComponent, LegendComponent,
  RadarComponent, VisualMapComponent, TitleComponent,
  CanvasRenderer,
])

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '320px' },
  width: { type: String, default: '100%' },
})
const el = ref(null)
let chart = null
let ro = null

function render() {
  if (!chart && el.value) chart = echarts.init(el.value)
  if (chart) chart.setOption(props.option || {}, true)
}
function onResize() {
  chart && chart.resize()
}

watch(() => props.option, () => nextTick(render), { deep: true })

onMounted(() => {
  render()
  ro = new ResizeObserver(onResize)
  ro.observe(el.value)
})
onBeforeUnmount(() => {
  ro && ro.disconnect()
  chart && chart.dispose()
  chart = null
})
</script>
