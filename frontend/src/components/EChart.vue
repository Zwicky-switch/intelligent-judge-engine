<template>
  <div ref="el" :style="{ height, width }"></div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

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
